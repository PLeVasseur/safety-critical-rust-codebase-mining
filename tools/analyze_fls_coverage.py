#!/usr/bin/env -S uv run python
"""
Analyze FLS coverage across coding standards mappings.

This script cross-references the coding standards FLS mappings with the
iceoryx2 FLS mapping files to generate frequency reports showing which
FLS sections are most referenced by safety-critical coding standards.

Usage:
    uv run python tools/analyze_fls_coverage.py
    uv run python tools/analyze_fls_coverage.py --output=report.json
    uv run python tools/analyze_fls_coverage.py --iceoryx2-only

Output:
    Prints a frequency report of FLS sections by reference count.
    Optionally outputs a JSON report file.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
MAPPINGS_DIR = ROOT_DIR / "coding-standards-fls-mapping" / "mappings"
ICEORYX2_FLS_DIR = ROOT_DIR / "iceoryx2-fls-mapping"
FLS_SECTION_MAPPING = SCRIPT_DIR / "fls_section_mapping.json"


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def load_fls_section_info() -> dict[str, dict]:
    """Load FLS section mapping with titles."""
    if not FLS_SECTION_MAPPING.exists():
        return {}

    data = load_json(FLS_SECTION_MAPPING)
    fls_info = {}

    def extract_info(obj: Any, chapter: str = "") -> None:
        if isinstance(obj, dict):
            if "fls_id" in obj and obj["fls_id"]:
                fls_id = obj["fls_id"]
                if not fls_id.startswith("fls_extracted"):
                    fls_info[fls_id] = {
                        "title": obj.get("title", "Unknown"),
                        "section": obj.get("fls_section", ""),
                        "chapter": chapter,
                    }
            # Get chapter from top-level
            if "chapter" in obj:
                chapter = str(obj["chapter"])
            for key, value in obj.items():
                extract_info(value, chapter)
        elif isinstance(obj, list):
            for item in obj:
                extract_info(item, chapter)

    extract_info(data)
    return fls_info


def collect_fls_references_from_standards() -> dict[str, list[str]]:
    """
    Collect all FLS ID references from coding standards mappings.

    Returns dict mapping FLS ID to list of guideline IDs that reference it.
    """
    fls_refs: dict[str, list[str]] = defaultdict(list)

    if not MAPPINGS_DIR.exists():
        return fls_refs

    for mapping_file in MAPPINGS_DIR.glob("*.json"):
        data = load_json(mapping_file)
        standard = data.get("standard", "unknown")

        for mapping in data.get("mappings", []):
            guideline_id = mapping.get("guideline_id", "unknown")
            full_id = f"{standard}:{guideline_id}"

            for fls_id in mapping.get("fls_ids", []):
                fls_refs[fls_id].append(full_id)

    return fls_refs


def collect_fls_usage_from_iceoryx2() -> dict[str, dict]:
    """
    Collect FLS section usage from iceoryx2-fls-mapping files.

    Returns dict mapping FLS ID to usage info (count, status, etc).
    """
    fls_usage = {}

    if not ICEORYX2_FLS_DIR.exists():
        return fls_usage

    def extract_usage(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            if "fls_ids" in obj and isinstance(obj["fls_ids"], list):
                for fls_id in obj["fls_ids"]:
                    if fls_id not in fls_usage:
                        fls_usage[fls_id] = {
                            "count": obj.get("count", 0),
                            "status": obj.get("status", "unknown"),
                            "samples": len(obj.get("samples", [])),
                            "section": obj.get("fls_section", ""),
                        }
            for key, value in obj.items():
                if key not in ("samples", "findings"):  # Skip large nested data
                    extract_usage(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                extract_usage(item, f"{path}[{i}]")

    for chapter_file in ICEORYX2_FLS_DIR.glob("fls_chapter*.json"):
        try:
            data = load_json(chapter_file)
            extract_usage(data)
        except Exception as e:
            print(f"Warning: Error reading {chapter_file}: {e}")

    return fls_usage


def generate_frequency_report(
    fls_refs: dict[str, list[str]],
    fls_usage: dict[str, dict],
    fls_info: dict[str, dict],
) -> list[dict]:
    """Generate a frequency report of FLS sections."""
    report = []

    # Get all FLS IDs from all sources
    all_fls_ids = set(fls_refs.keys()) | set(fls_usage.keys()) | set(fls_info.keys())

    for fls_id in all_fls_ids:
        refs = fls_refs.get(fls_id, [])
        usage = fls_usage.get(fls_id, {})
        info = fls_info.get(fls_id, {})

        entry = {
            "fls_id": fls_id,
            "title": info.get("title", "Unknown"),
            "section": info.get("section", usage.get("section", "")),
            "chapter": info.get("chapter", ""),
            "standard_references": len(refs),
            "referencing_guidelines": refs,
            "iceoryx2_count": usage.get("count", 0),
            "iceoryx2_status": usage.get("status", "not_found"),
            "iceoryx2_samples": usage.get("samples", 0),
        }
        report.append(entry)

    # Sort by standard references (descending), then by iceoryx2 count
    report.sort(key=lambda x: (-x["standard_references"], -(x["iceoryx2_count"] or 0)))

    return report


def print_summary(report: list[dict]) -> None:
    """Print a summary of the analysis."""
    print("=" * 80)
    print("FLS Coverage Analysis Report")
    print("=" * 80)

    # Count statistics
    total_fls_ids = len(report)
    referenced_by_standards = sum(1 for r in report if r["standard_references"] > 0)
    used_in_iceoryx2 = sum(1 for r in report if (r["iceoryx2_count"] or 0) > 0)
    both = sum(
        1 for r in report if r["standard_references"] > 0 and (r["iceoryx2_count"] or 0) > 0
    )

    print(f"\nTotal FLS sections: {total_fls_ids}")
    print(f"Referenced by coding standards: {referenced_by_standards}")
    print(f"Used in iceoryx2: {used_in_iceoryx2}")
    print(f"Both: {both}")

    # Top referenced sections
    print("\n" + "-" * 80)
    print("Top 20 FLS Sections by Coding Standard References")
    print("-" * 80)
    print(f"{'FLS ID':<25} {'Section':<10} {'Refs':>5} {'Title':<40}")
    print("-" * 80)

    for entry in report[:20]:
        if entry["standard_references"] == 0:
            break
        title = entry["title"][:38] + ".." if len(entry["title"]) > 40 else entry["title"]
        print(
            f"{entry['fls_id']:<25} {entry['section']:<10} "
            f"{entry['standard_references']:>5} {title:<40}"
        )

    # Breakdown by standard
    print("\n" + "-" * 80)
    print("References by Coding Standard")
    print("-" * 80)

    standard_counts = Counter()
    for entry in report:
        for ref in entry["referencing_guidelines"]:
            standard = ref.split(":")[0]
            standard_counts[standard] += 1

    for standard, count in standard_counts.most_common():
        print(f"  {standard}: {count} FLS references")

    # Most referenced sections per standard
    print("\n" + "-" * 80)
    print("Top 5 FLS Sections per Standard")
    print("-" * 80)

    for standard in ["MISRA-C", "MISRA-C++", "CERT-C", "CERT-C++"]:
        print(f"\n{standard}:")
        section_refs = Counter()
        for entry in report:
            for ref in entry["referencing_guidelines"]:
                if ref.startswith(standard + ":"):
                    section_refs[entry["fls_id"]] += 1

        if section_refs:
            for fls_id, count in section_refs.most_common(5):
                info = next((r for r in report if r["fls_id"] == fls_id), {})
                title = info.get("title", "Unknown")[:30]
                print(f"  {fls_id}: {count} refs - {title}")
        else:
            print("  (no mappings yet)")

    # Iceoryx2 intersection
    print("\n" + "-" * 80)
    print("High-Priority Sections (Referenced by Standards AND Used in iceoryx2)")
    print("-" * 80)

    priority_sections = [
        r for r in report
        if r["standard_references"] > 0 and (r["iceoryx2_count"] or 0) > 0
    ]
    priority_sections.sort(key=lambda x: -x["standard_references"] * (x["iceoryx2_count"] or 0))

    if priority_sections:
        print(f"{'FLS ID':<25} {'Refs':>5} {'Count':>7} {'Title':<40}")
        print("-" * 80)
        for entry in priority_sections[:15]:
            title = entry["title"][:38] + ".." if len(entry["title"]) > 40 else entry["title"]
            print(
                f"{entry['fls_id']:<25} {entry['standard_references']:>5} "
                f"{entry['iceoryx2_count']:>7} {title:<40}"
            )
    else:
        print("  (no overlapping mappings yet - populate mapping files first)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze FLS coverage across coding standards mappings"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON report to file",
    )
    parser.add_argument(
        "--iceoryx2-only",
        action="store_true",
        help="Only show FLS sections used in iceoryx2",
    )
    args = parser.parse_args()

    # Load data
    print("Loading FLS section information...")
    fls_info = load_fls_section_info()
    print(f"  Found {len(fls_info)} FLS sections with metadata")

    print("Collecting references from coding standards mappings...")
    fls_refs = collect_fls_references_from_standards()
    print(f"  Found {sum(len(v) for v in fls_refs.values())} total references")

    print("Collecting usage from iceoryx2-fls-mapping...")
    fls_usage = collect_fls_usage_from_iceoryx2()
    print(f"  Found {len(fls_usage)} FLS sections with usage data")

    # Generate report
    report = generate_frequency_report(fls_refs, fls_usage, fls_info)

    if args.iceoryx2_only:
        report = [r for r in report if r["iceoryx2_count"] > 0]

    # Print summary
    print_summary(report)

    # Output JSON if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report saved to {output_path}")


if __name__ == "__main__":
    main()
