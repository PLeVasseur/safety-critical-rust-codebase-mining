#!/usr/bin/env -S uv run python
"""
Validate coding standards JSON files against their schemas.

This script validates:
1. Standards files (MISRA/CERT rule listings) against coding_standard_rules.schema.json
2. Mapping files (FLS mappings) against fls_mapping.schema.json
3. FLS ID references against the canonical FLS section mapping AND native RST source
4. FLS IDs in fls_ids, accepted_matches, and rejected_matches arrays

Usage:
    uv run python tools/validate_coding_standards.py
    uv run python tools/validate_coding_standards.py --file=misra_c_2025.json
    uv run python tools/validate_coding_standards.py --mappings-only

Exit Codes:
    0 - All validations pass
    1 - Schema validation failed
    2 - FLS ID validation failed
    3 - Multiple failures
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_coding_standards_dir,
    get_tools_dir,
    get_guideline_schema_version,
    is_v1,
    is_v2,
    has_add6_data,
    count_matches_by_category,
    validate_paragraph_coverage,
    has_paragraph_coverage_fields,
)

# Use shared path utilities to get correct paths
ROOT_DIR = get_project_root()
CODING_STANDARDS_DIR = get_coding_standards_dir()
STANDARDS_DIR = CODING_STANDARDS_DIR / "standards"
MAPPINGS_DIR = CODING_STANDARDS_DIR / "mappings"
SCHEMA_DIR = CODING_STANDARDS_DIR / "schema"
TOOLS_DATA_DIR = get_tools_dir() / "data"
FLS_MAPPING_PATH = TOOLS_DATA_DIR / "fls_section_mapping.json"
FLS_RST_DIR = ROOT_DIR / "cache" / "repos" / "fls" / "src"
SYNTHETIC_IDS_PATH = TOOLS_DATA_DIR / "synthetic_fls_ids.json"

# Schema file names
RULES_SCHEMA = "coding_standard_rules.schema.json"
MAPPING_SCHEMA = "fls_mapping.schema.json"


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def load_native_fls_ids_from_rst() -> set[str]:
    """Load all FLS IDs from the FLS RST source files."""
    ids = set()
    if not FLS_RST_DIR.exists():
        return ids

    for rst_file in FLS_RST_DIR.glob("*.rst"):
        content = rst_file.read_text()
        # Match FLS ID anchors like .. _fls_abc123:
        ids.update(re.findall(r'fls_[a-zA-Z0-9]+', content))

    return ids


def load_synthetic_fls_ids() -> set[str]:
    """Load tracked synthetic FLS IDs."""
    if not SYNTHETIC_IDS_PATH.exists():
        return set()
    
    data = load_json(SYNTHETIC_IDS_PATH)
    return set(data.get("synthetic_ids", {}).keys())


def load_fls_ids_from_mapping() -> set[str]:
    """Load all valid FLS IDs from the FLS section mapping."""
    if not FLS_MAPPING_PATH.exists():
        print(f"Warning: FLS section mapping not found at {FLS_MAPPING_PATH}")
        return set()

    fls_data = load_json(FLS_MAPPING_PATH)
    fls_ids = set()

    def extract_ids(obj: Any) -> None:
        """Recursively extract FLS IDs from the mapping."""
        if isinstance(obj, dict):
            if "fls_id" in obj and obj["fls_id"]:
                # Skip synthetic IDs marked with special prefix
                if not obj["fls_id"].startswith("fls_extracted"):
                    fls_ids.add(obj["fls_id"])
            for value in obj.values():
                extract_ids(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_ids(item)

    extract_ids(fls_data)
    return fls_ids


def load_all_valid_fls_ids() -> tuple[set[str], set[str], set[str]]:
    """Load all valid FLS IDs from all sources.
    
    Returns:
        Tuple of (native_ids, synthetic_ids, mapping_ids)
    """
    native_ids = load_native_fls_ids_from_rst()
    synthetic_ids = load_synthetic_fls_ids()
    mapping_ids = load_fls_ids_from_mapping()
    return native_ids, synthetic_ids, mapping_ids


def validate_schema(data: dict, schema: dict, filename: str) -> list[str]:
    """Validate data against a JSON schema. Returns list of errors."""
    errors = []
    validator = jsonschema.Draft202012Validator(schema)

    for error in validator.iter_errors(data):
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        errors.append(f"{filename}: {path}: {error.message}")

    return errors


def validate_fls_ids(data: dict, valid_fls_ids: set[str], filename: str) -> list[str]:
    """Validate that all FLS IDs in a mapping file are valid.
    
    Handles v1.x (flat) and v2.x/v3.x/v4.x (per-context) formats.
    
    Checks FLS IDs in:
    - fls_ids array (v1.x)
    - accepted_matches array (v1.x or v2.x+ context)
    - rejected_matches array (v1.x or v2.x+ context)
    """
    errors = []

    if "mappings" not in data:
        return errors

    # Per-context versions
    per_context_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")

    def check_matches(matches: list, location: str, guideline_id: str) -> None:
        """Helper to check FLS IDs in a matches array."""
        for match in matches:
            fls_id = match.get("fls_id")
            if fls_id and fls_id not in valid_fls_ids:
                errors.append(f"{filename}: {guideline_id}: Unknown FLS ID '{fls_id}' in {location}")

    for mapping in data["mappings"]:
        guideline_id = mapping.get("guideline_id", "unknown")
        schema_version = get_guideline_schema_version(mapping)
        
        if schema_version in ("1.0", "1.1", "1.2"):
            # v1.x: Check flat structure
            fls_ids = mapping.get("fls_ids", [])
            for fls_id in fls_ids:
                if fls_id not in valid_fls_ids:
                    errors.append(f"{filename}: {guideline_id}: Unknown FLS ID '{fls_id}' in fls_ids")
            
            check_matches(mapping.get("accepted_matches", []), "accepted_matches", guideline_id)
            check_matches(mapping.get("rejected_matches", []), "rejected_matches", guideline_id)
        
        elif schema_version in per_context_versions:
            # v2.x/v3.x/v4.x: Check per-context structure
            for context in ["all_rust", "safe_rust"]:
                ctx_data = mapping.get(context, {})
                check_matches(ctx_data.get("accepted_matches", []), f"{context}.accepted_matches", guideline_id)
                check_matches(ctx_data.get("rejected_matches", []), f"{context}.rejected_matches", guideline_id)

    return errors


def validate_standards_file(filepath: Path, schema: dict) -> tuple[list[str], dict]:
    """Validate a standards file and return errors and statistics."""
    data = load_json(filepath)
    errors = validate_schema(data, schema, filepath.name)

    # Compute statistics for verification
    stats = {
        "standard": data.get("standard", "unknown"),
        "version": data.get("version", "unknown"),
        "categories": len(data.get("categories", [])),
        "guidelines": sum(
            len(cat.get("guidelines", []))
            for cat in data.get("categories", [])
        ),
    }

    return errors, stats


def validate_mapping_file(
    filepath: Path, schema: dict, valid_fls_ids: set[str]
) -> tuple[list[str], dict, list[str]]:
    """Validate a mapping file and return errors, statistics, and warnings.
    
    Handles v1.x (flat) and v2.x/v3.x/v4.x (per-context) formats.
    
    Returns:
        (errors, stats, warnings)
    """
    data = load_json(filepath)
    errors = validate_schema(data, schema, filepath.name)
    warnings = []

    # Validate FLS IDs
    fls_errors = validate_fls_ids(data, valid_fls_ids, filepath.name)
    errors.extend(fls_errors)

    # Compute statistics for both applicability dimensions
    mappings = data.get("mappings", [])
    
    # Count entries by schema version
    version_counts = {
        "1.0": 0, "1.1": 0, "1.2": 0,
        "2.0": 0, "2.1": 0, "2.2": 0,
        "3.0": 0, "3.1": 0, "3.2": 0,
        "4.0": 0,
    }
    for m in mappings:
        v = get_guideline_schema_version(m)
        if v in version_counts:
            version_counts[v] += 1
    
    # Count entries with ADD-6 data
    add6_count = sum(1 for m in mappings if has_add6_data(m))
    
    # Count paragraph coverage
    para_stats = {
        "with_paragraphs": 0,
        "section_only": 0,
        "no_matches": 0,
        "has_waiver": 0,
        "coverage_errors": 0,
    }
    
    # Warn if enriched versions (1.1+, 2.1+, 3.x, 4.x) are missing ADD-6 data
    add6_versions = ("1.1", "1.2", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    for m in mappings:
        v = get_guideline_schema_version(m)
        gid = m.get("guideline_id", "unknown")
        
        if v in add6_versions and not has_add6_data(m):
            warnings.append(f"{filepath.name}: {gid}: v{v} entry missing misra_add6 block")
        
        # Validate paragraph coverage
        para_errors = validate_paragraph_coverage(m, strict=False)
        if para_errors:
            para_stats["coverage_errors"] += 1
            for err in para_errors:
                warnings.append(f"{filepath.name}: {gid}: {err}")
        
        # Count paragraph coverage categories
        if has_paragraph_coverage_fields(m):
            if v.startswith("1."):
                para_count = m.get("paragraph_match_count", 0)
                section_count = m.get("section_match_count", 0)
                has_waiver = m.get("paragraph_level_waiver") is not None
            else:
                # Per-context: count both contexts
                para_count = 0
                section_count = 0
                has_waiver = False
                for ctx in ["all_rust", "safe_rust"]:
                    ctx_data = m.get(ctx, {})
                    para_count += ctx_data.get("paragraph_match_count", 0)
                    section_count += ctx_data.get("section_match_count", 0)
                    if ctx_data.get("paragraph_level_waiver"):
                        has_waiver = True
            
            if para_count > 0:
                para_stats["with_paragraphs"] += 1
            elif section_count > 0:
                para_stats["section_only"] += 1
            else:
                para_stats["no_matches"] += 1
            
            if has_waiver:
                para_stats["has_waiver"] += 1
    
    v1_versions = ("1.0", "1.1", "1.2")
    v2_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    
    def count_v1_applicability(field: str) -> dict[str, int]:
        """Count v1.x applicability values for a given field."""
        v1_mappings = [m for m in mappings if get_guideline_schema_version(m) in v1_versions]
        return {
            "direct": sum(1 for m in v1_mappings if m.get(field) == "direct"),
            "partial": sum(1 for m in v1_mappings if m.get(field) == "partial"),
            "not_applicable": sum(1 for m in v1_mappings if m.get(field) == "not_applicable"),
            "rust_prevents": sum(1 for m in v1_mappings if m.get(field) == "rust_prevents"),
            "unmapped": sum(1 for m in v1_mappings if m.get(field) == "unmapped"),
        }
    
    def count_v2_applicability(context: str) -> dict[str, int]:
        """Count v2.x+ applicability values for a given context."""
        v2_mappings = [m for m in mappings if get_guideline_schema_version(m) in v2_versions]
        counts = {"yes": 0, "no": 0, "partial": 0}
        for m in v2_mappings:
            ctx = m.get(context, {})
            app = ctx.get("applicability", "no")
            if app in counts:
                counts[app] += 1
        return counts
    
    v1_total = sum(version_counts.get(v, 0) for v in v1_versions)
    v2_total = sum(version_counts.get(v, 0) for v in v2_versions)
    
    stats = {
        "standard": data.get("standard", "unknown"),
        "total": len(mappings),
        "version_counts": version_counts,
        "v1_count": v1_total,
        "v2_count": v2_total,
        "add6_count": add6_count,
        "paragraph_coverage": para_stats,
        "all_rust": count_v1_applicability("applicability_all_rust"),
        "safe_rust": count_v1_applicability("applicability_safe_rust"),
    }
    
    # Add v2 stats if any v2+ entries exist
    if v2_total > 0:
        stats["all_rust_v2"] = count_v2_applicability("all_rust")
        stats["safe_rust_v2"] = count_v2_applicability("safe_rust")

    return errors, stats, warnings


def check_guideline_coverage(standards_file: Path, mapping_file: Path) -> list[str]:
    """Check that all guidelines in a standards file have mapping entries."""
    errors = []

    if not standards_file.exists() or not mapping_file.exists():
        return errors

    standards_data = load_json(standards_file)
    mapping_data = load_json(mapping_file)

    # Get all guideline IDs from standards file
    standard_ids = set()
    for cat in standards_data.get("categories", []):
        for g in cat.get("guidelines", []):
            standard_ids.add(g.get("id"))

    # Get all guideline IDs from mapping file
    mapped_ids = {m.get("guideline_id") for m in mapping_data.get("mappings", [])}

    # Find missing mappings
    missing = standard_ids - mapped_ids
    if missing:
        for gid in sorted(missing):
            errors.append(
                f"{mapping_file.name}: Missing mapping for guideline '{gid}'"
            )

    # Find extra mappings (mappings for non-existent guidelines)
    extra = mapped_ids - standard_ids
    if extra:
        for gid in sorted(extra):
            errors.append(
                f"{mapping_file.name}: Mapping for unknown guideline '{gid}'"
            )

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate coding standards JSON files")
    parser.add_argument(
        "--file",
        help="Validate only this specific file (in standards/ or mappings/)",
    )
    parser.add_argument(
        "--mappings-only",
        action="store_true",
        help="Only validate mapping files",
    )
    parser.add_argument(
        "--standards-only",
        action="store_true",
        help="Only validate standards files",
    )
    parser.add_argument(
        "--check-coverage",
        action="store_true",
        help="Check that all guidelines have mapping entries",
    )
    args = parser.parse_args()

    # Load schemas
    rules_schema_path = SCHEMA_DIR / RULES_SCHEMA
    mapping_schema_path = SCHEMA_DIR / MAPPING_SCHEMA

    if not rules_schema_path.exists():
        print(f"Error: Rules schema not found at {rules_schema_path}")
        sys.exit(1)
    if not mapping_schema_path.exists():
        print(f"Error: Mapping schema not found at {mapping_schema_path}")
        sys.exit(1)

    rules_schema = load_json(rules_schema_path)
    mapping_schema = load_json(mapping_schema_path)

    # Load valid FLS IDs from all sources
    native_ids, synthetic_ids, mapping_ids = load_all_valid_fls_ids()
    valid_fls_ids = native_ids | synthetic_ids
    print(f"Loaded FLS IDs:")
    print(f"  Native (from RST):     {len(native_ids)}")
    print(f"  Synthetic (tracked):   {len(synthetic_ids)}")
    print(f"  In section mapping:    {len(mapping_ids)}")
    print(f"  Total valid:           {len(valid_fls_ids)}")

    all_errors = []
    schema_errors = []
    fls_errors = []

    # Validate standards files
    if not args.mappings_only:
        print("\n" + "=" * 60)
        print("Validating Standards Files")
        print("=" * 60)

        standards_files = list(STANDARDS_DIR.glob("*.json")) if STANDARDS_DIR.exists() else []

        if args.file:
            standards_files = [f for f in standards_files if f.name == args.file]

        for filepath in sorted(standards_files):
            print(f"\n  {filepath.name}:")
            errors, stats = validate_standards_file(filepath, rules_schema)

            if errors:
                schema_errors.extend(errors)
                print(f"    FAILED: {len(errors)} error(s)")
                for e in errors[:5]:
                    print(f"      - {e}")
                if len(errors) > 5:
                    print(f"      ... and {len(errors) - 5} more")
            else:
                print(f"    OK - {stats['standard']} {stats['version']}")
                print(f"       {stats['categories']} categories, {stats['guidelines']} guidelines")

    # Validate mapping files
    if not args.standards_only:
        print("\n" + "=" * 60)
        print("Validating Mapping Files")
        print("=" * 60)

        mapping_files = list(MAPPINGS_DIR.glob("*.json")) if MAPPINGS_DIR.exists() else []

        if args.file:
            mapping_files = [f for f in mapping_files if f.name == args.file]

        if not mapping_files:
            print("\n  No mapping files found (expected in mappings/ directory)")
        else:
            all_warnings = []
            for filepath in sorted(mapping_files):
                print(f"\n  {filepath.name}:")
                errors, stats, warnings = validate_mapping_file(filepath, mapping_schema, valid_fls_ids)
                all_warnings.extend(warnings)

                schema_err = [e for e in errors if "Unknown FLS ID" not in e]
                fls_err = [e for e in errors if "Unknown FLS ID" in e]

                if schema_err:
                    schema_errors.extend(schema_err)
                    print(f"    Schema errors: {len(schema_err)}")
                    for e in schema_err[:3]:
                        print(f"      - {e}")

                if fls_err:
                    fls_errors.extend(fls_err)
                    print(f"    FLS ID errors: {len(fls_err)}")
                    for e in fls_err[:3]:
                        print(f"      - {e}")

                if warnings:
                    print(f"    Warnings: {len(warnings)}")
                    for w in warnings[:3]:
                        print(f"      - {w}")

                if not errors:
                    print(f"    OK - {stats['standard']} ({stats['total']} guidelines)")
                    
                    # Show version breakdown
                    vc = stats.get("version_counts", {})
                    version_parts = []
                    for v in ["1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0"]:
                        if vc.get(v, 0) > 0:
                            version_parts.append(f"v{v}={vc[v]}")
                    if version_parts:
                        print(f"       Schema versions: {', '.join(version_parts)}")
                    
                    # Show ADD-6 coverage
                    add6_count = stats.get("add6_count", 0)
                    total = stats.get("total", 0)
                    print(f"       ADD-6 data: {add6_count}/{total} entries")
                    
                    # Show paragraph coverage
                    para = stats.get("paragraph_coverage", {})
                    if para:
                        with_para = para.get("with_paragraphs", 0)
                        sect_only = para.get("section_only", 0)
                        no_match = para.get("no_matches", 0)
                        has_waiver = para.get("has_waiver", 0)
                        cov_err = para.get("coverage_errors", 0)
                        
                        # Only show if any entries have paragraph coverage fields
                        if with_para + sect_only + no_match > 0:
                            print(f"       Paragraph coverage: {with_para} have paragraphs, "
                                  f"{sect_only} section-only, {no_match} no matches")
                            if has_waiver > 0:
                                print(f"       Paragraph waivers: {has_waiver}")
                            if cov_err > 0:
                                print(f"       Paragraph coverage errors: {cov_err}")
                    
                    if stats['v1_count'] > 0:
                        all_rust = stats["all_rust"]
                        safe_rust = stats["safe_rust"]
                        print(
                            f"       [v1.x] All Rust:  {all_rust['direct']} direct, "
                            f"{all_rust['partial']} partial, "
                            f"{all_rust['not_applicable']} N/A, "
                            f"{all_rust['rust_prevents']} rust_prevents"
                        )
                        print(
                            f"       [v1.x] Safe Rust: {safe_rust['direct']} direct, "
                            f"{safe_rust['partial']} partial, "
                            f"{safe_rust['not_applicable']} N/A, "
                            f"{safe_rust['rust_prevents']} rust_prevents"
                        )
                    
                    if stats['v2_count'] > 0:
                        all_rust_v2 = stats.get("all_rust_v2", {})
                        safe_rust_v2 = stats.get("safe_rust_v2", {})
                        print(
                            f"       [v2.x+] All Rust:  {all_rust_v2.get('yes', 0)} yes, "
                            f"{all_rust_v2.get('partial', 0)} partial, "
                            f"{all_rust_v2.get('no', 0)} no"
                        )
                        print(
                            f"       [v2.x+] Safe Rust: {safe_rust_v2.get('yes', 0)} yes, "
                            f"{safe_rust_v2.get('partial', 0)} partial, "
                            f"{safe_rust_v2.get('no', 0)} no"
                        )

    # Check guideline coverage
    if args.check_coverage:
        print("\n" + "=" * 60)
        print("Checking Guideline Coverage")
        print("=" * 60)

        coverage_pairs = [
            (STANDARDS_DIR / "misra_c_2025.json", MAPPINGS_DIR / "misra_c_to_fls.json"),
            (STANDARDS_DIR / "misra_cpp_2023.json", MAPPINGS_DIR / "misra_cpp_to_fls.json"),
            (STANDARDS_DIR / "cert_c.json", MAPPINGS_DIR / "cert_c_to_fls.json"),
            (STANDARDS_DIR / "cert_cpp.json", MAPPINGS_DIR / "cert_cpp_to_fls.json"),
        ]

        for standards_file, mapping_file in coverage_pairs:
            if standards_file.exists() and mapping_file.exists():
                errors = check_guideline_coverage(standards_file, mapping_file)
                if errors:
                    all_errors.extend(errors)
                    print(f"\n  {mapping_file.name}: {len(errors)} coverage issues")
                    for e in errors[:5]:
                        print(f"    - {e}")
                else:
                    print(f"\n  {mapping_file.name}: Full coverage")

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    all_errors = schema_errors + fls_errors

    if not all_errors:
        print("\n  All validations passed!")
        sys.exit(0)
    else:
        print(f"\n  Schema errors: {len(schema_errors)}")
        print(f"  FLS ID errors: {len(fls_errors)}")
        print(f"  Total errors: {len(all_errors)}")

        # Determine exit code
        exit_code = 0
        if schema_errors:
            exit_code |= 1
        if fls_errors:
            exit_code |= 2
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
