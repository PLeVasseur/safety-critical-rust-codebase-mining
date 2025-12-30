#!/usr/bin/env python3
"""
Validate FLS mapping JSON files against schema and FLS section mapping.

This script performs comprehensive validation of the FLS chapter mapping files:

1. Schema Validation - Validates JSON structure against schema.json
2. MUST_BE_FILLED Detection - Finds placeholder markers needing completion
3. Sample Path Validation - Verifies code sample paths exist in iceoryx2 repo
4. FLS Coverage Check - Ensures all FLS sections are documented
5. FLS ID Validation - Verifies fls_ids match canonical FLS identifiers
6. Section Hierarchy Validation - Checks fls_section numbering is well-formed

Exit Codes:
    0 - All checks pass
    1 - Schema validation failed (invalid JSON structure)
    2 - FLS coverage check failed (missing required sections)
    3 - FLS ID validation failed (invalid IDs found)
    4 - Multiple failures (combination of above)

Usage:
    # Validate all files with full recursive depth
    uv run python tools/validate_fls_json.py

    # Validate with limited depth (e.g., top-level sections only)
    uv run python tools/validate_fls_json.py --depth=1

    # Validate a specific file
    uv run python tools/validate_fls_json.py --file=fls_chapter13_attributes.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import jsonschema


SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
MAPPING_DIR = ROOT_DIR / "iceoryx2-fls-mapping"
SCHEMA_PATH = MAPPING_DIR / "schema.json"
FLS_MAPPING_PATH = SCRIPT_DIR / "fls_section_mapping.json"
ICEORYX2_CACHE = ROOT_DIR / "cache" / "repos" / "iceoryx2"

# Top-level keys in chapter JSON that are not FLS sections
# These are valid per schema but not part of the FLS hierarchy
NON_SECTION_KEYS = {
    "design_patterns",
    "cross_chapter_references",
    "safety_critical_summary",
}

# Sentinel value for sections extracted from syntax blocks (no native FLS ID)
FLS_EXTRACTED_FROM_SYNTAX = "fls_extracted_from_syntax_block"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate FLS mapping JSON files against schema and FLS section mapping.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit Codes:
  0  All checks pass
  1  Schema validation failed (invalid JSON structure)
  2  FLS coverage check failed (missing required sections)
  3  FLS ID validation failed (invalid IDs found)
  4  Multiple failures (combination of above)

Examples:
  # Validate all files with full recursive depth
  uv run python tools/validate_fls_json.py

  # Validate top-level sections only (depth=1)
  uv run python tools/validate_fls_json.py --depth=1

  # Validate two levels deep (e.g., 13.1, 13.2, 13.2.1 but not 13.2.1.1)
  uv run python tools/validate_fls_json.py --depth=2

  # Validate a specific file
  uv run python tools/validate_fls_json.py --file=fls_chapter13_attributes.json
""",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Maximum depth for coverage check (default: unlimited). "
        "Depth 1 = top-level sections only, 2 = includes first-level subsections, etc.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Validate a specific file instead of all files (e.g., fls_chapter13_attributes.json)",
    )
    return parser.parse_args()


def load_schema() -> Dict:
    """Load the JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_fls_mapping() -> Dict:
    """Load the canonical FLS section mapping."""
    with open(FLS_MAPPING_PATH) as f:
        return json.load(f)


def find_must_be_filled(obj: Any, path: str = "") -> List[str]:
    """
    Recursively find all MUST_BE_FILLED markers.

    Returns list of JSON paths where markers are found.
    """
    results = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            if value == "MUST_BE_FILLED":
                results.append(new_path)
            else:
                results.extend(find_must_be_filled(value, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            results.extend(find_must_be_filled(item, new_path))
    elif obj == "MUST_BE_FILLED":
        results.append(path)

    return results


def find_sample_paths(obj: Any, path: str = "") -> List[Tuple[str, str, List[int]]]:
    """
    Recursively find all code sample file paths.

    Returns list of (json_path, file_path, line_numbers).
    """
    results = []

    if isinstance(obj, dict):
        if "file" in obj and "line" in obj:
            # This is a sample
            file_path = obj.get("file", "")
            line_nums = obj.get("line", [])
            if file_path and file_path != "MUST_BE_FILLED":
                results.append((path, file_path, line_nums))
        else:
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                results.extend(find_sample_paths(value, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            results.extend(find_sample_paths(item, new_path))

    return results


def validate_sample_paths(
    samples: List[Tuple[str, str, List[int]]], version: str
) -> List[str]:
    """
    Validate that sample file paths exist in the iceoryx2 repo.

    Returns list of error messages.
    """
    errors = []
    repo_path = ICEORYX2_CACHE / f"v{version}"

    if not repo_path.exists():
        return [f"iceoryx2 repo not found at {repo_path}. Skipping path validation."]

    for json_path, file_path, line_nums in samples:
        full_path = repo_path / file_path
        if not full_path.exists():
            errors.append(f"{json_path}: File not found: {file_path}")
        elif line_nums:
            # Handle line_nums that might be int instead of list
            if isinstance(line_nums, int):
                line_nums = [line_nums]
            elif not isinstance(line_nums, list):
                continue  # Skip invalid line_nums

            # Optionally verify line numbers exist
            try:
                with open(full_path) as f:
                    lines = f.readlines()
                    max_line = len(lines)
                    for line_num in line_nums:
                        if line_num > max_line:
                            errors.append(
                                f"{json_path}: Line {line_num} exceeds file length ({max_line}): {file_path}"
                            )
            except Exception as e:
                errors.append(f"{json_path}: Error reading {file_path}: {e}")

    return errors


def get_section_depth(fls_section: str) -> int:
    """
    Get the depth of a section number.

    Examples:
        "13" -> 0 (chapter level)
        "13.1" -> 1
        "13.2.1" -> 2
        "13.2.1.1" -> 3
    """
    if not fls_section:
        return 0
    parts = fls_section.split(".")
    return len(parts) - 1


def collect_fls_sections_from_mapping(
    mapping_sections: Dict, max_depth: Optional[int] = None, current_depth: int = 1
) -> Dict[str, Dict]:
    """
    Recursively collect all FLS sections from the mapping.

    Returns dict mapping fls_section numbers to section info.
    """
    sections = {}

    for key, section in mapping_sections.items():
        if not isinstance(section, dict):
            continue

        fls_section = section.get("fls_section")
        if fls_section:
            sections[fls_section] = {
                "key": key,
                "title": section.get("title", ""),
                "fls_id": section.get("fls_id"),
            }

        # Recurse into subsections if within depth limit
        if max_depth is None or current_depth < max_depth:
            subsections = section.get("subsections", {})
            if subsections:
                sections.update(
                    collect_fls_sections_from_mapping(
                        subsections, max_depth, current_depth + 1
                    )
                )

    return sections


def collect_fls_sections_from_json(
    json_sections: Dict, max_depth: Optional[int] = None, current_depth: int = 1
) -> Dict[str, Dict]:
    """
    Recursively collect all FLS sections from a chapter JSON.

    Returns dict mapping fls_section numbers to section info.
    """
    sections = {}

    for key, section in json_sections.items():
        if not isinstance(section, dict):
            continue

        fls_section = section.get("fls_section")
        if fls_section:
            sections[fls_section] = {
                "key": key,
                "fls_ids": section.get("fls_ids", []),
                "status": section.get("status", ""),
            }

        # Recurse into subsections if within depth limit
        if max_depth is None or current_depth < max_depth:
            subsections = section.get("subsections", {})
            if subsections:
                sections.update(
                    collect_fls_sections_from_json(
                        subsections, max_depth, current_depth + 1
                    )
                )

    return sections


def collect_fls_ids_from_mapping(mapping_sections: Dict) -> Dict[str, str]:
    """
    Recursively collect all FLS IDs from the mapping.

    Returns dict mapping fls_id to fls_section.
    """
    ids = {}

    for key, section in mapping_sections.items():
        if not isinstance(section, dict):
            continue

        fls_id = section.get("fls_id")
        fls_section = section.get("fls_section", "")
        if fls_id and fls_id != "fls_extracted_from_syntax_block":
            ids[fls_id] = fls_section

        subsections = section.get("subsections", {})
        if subsections:
            ids.update(collect_fls_ids_from_mapping(subsections))

    return ids


def collect_fls_ids_from_json(json_sections: Dict) -> Tuple[List[Tuple[str, str]], int]:
    """
    Recursively collect all FLS IDs from a chapter JSON.

    Returns tuple of:
        - list of (fls_id, json_path) tuples
        - count of sections using the syntax extraction sentinel
    """
    ids = []
    syntax_extracted_count = 0

    def collect(sections: Dict, path: str = ""):
        nonlocal syntax_extracted_count
        for key, section in sections.items():
            if not isinstance(section, dict):
                continue

            current_path = f"{path}.{key}" if path else key
            fls_ids = section.get("fls_ids", [])
            for fls_id in fls_ids:
                if fls_id == FLS_EXTRACTED_FROM_SYNTAX:
                    syntax_extracted_count += 1
                elif fls_id and fls_id != "MUST_BE_FILLED":
                    ids.append((fls_id, current_path))

            subsections = section.get("subsections", {})
            if subsections:
                collect(subsections, current_path)

    collect(json_sections)
    return ids, syntax_extracted_count


def validate_fls_coverage(
    data: Dict, chapter_mapping: Dict, max_depth: Optional[int] = None
) -> Dict:
    """
    Check that all FLS sections from the mapping are covered in the JSON.

    Returns dict with:
        - missing_sections: list of (fls_section, title) tuples not in the JSON
        - extra_sections: list of section keys in JSON not in FLS mapping (informational)
        - coverage_percent: percentage of FLS sections covered
    """
    result = {
        "missing_sections": [],
        "extra_sections": [],
        "coverage_percent": 0.0,
        "total_expected": 0,
        "total_found": 0,
    }

    mapping_sections = chapter_mapping.get("sections", {})
    json_sections = data.get("sections", {})

    # Collect sections from both sources
    expected = collect_fls_sections_from_mapping(mapping_sections, max_depth)
    actual = collect_fls_sections_from_json(json_sections, max_depth)

    result["total_expected"] = len(expected)

    # Find missing sections
    for fls_section, info in expected.items():
        if fls_section not in actual:
            result["missing_sections"].append((fls_section, info["title"]))

    result["total_found"] = result["total_expected"] - len(result["missing_sections"])

    # Calculate coverage
    if result["total_expected"] > 0:
        result["coverage_percent"] = (
            result["total_found"] / result["total_expected"]
        ) * 100

    # Find extra sections (in JSON but not in mapping) - informational only
    expected_section_nums = set(expected.keys())
    for fls_section in actual.keys():
        if fls_section not in expected_section_nums:
            result["extra_sections"].append(fls_section)

    # Also check for top-level extra keys (design_patterns, etc.)
    for key in data.keys():
        if key in NON_SECTION_KEYS:
            result["extra_sections"].append(f"(top-level) {key}")

    return result


def validate_fls_ids(data: Dict, chapter_mapping: Dict) -> Dict:
    """
    Validate that fls_ids in the JSON match canonical IDs from the mapping.

    Returns dict with:
        - valid_count: count of valid IDs
        - invalid_ids: list of (fls_id, json_path) tuples not found in mapping
        - unmapped_in_fls: count of sections where FLS source has no ID (OK)
        - syntax_extracted: count of sections using the syntax extraction sentinel
    """
    result = {
        "valid_count": 0,
        "invalid_ids": [],
        "unmapped_in_fls": 0,
        "syntax_extracted": 0,
    }

    mapping_sections = chapter_mapping.get("sections", {})
    json_sections = data.get("sections", {})

    # Get canonical IDs from mapping
    canonical_ids = collect_fls_ids_from_mapping(mapping_sections)
    # Also include the chapter-level fls_id
    chapter_fls_id = chapter_mapping.get("fls_id")
    if chapter_fls_id:
        canonical_ids[chapter_fls_id] = "chapter"

    # Get IDs from JSON
    json_ids, syntax_extracted_count = collect_fls_ids_from_json(json_sections)
    result["syntax_extracted"] = syntax_extracted_count
    
    # Also check chapter-level fls_id
    if data.get("fls_id"):
        json_ids.append((data["fls_id"], "(chapter level)"))

    # Validate each ID
    for fls_id, json_path in json_ids:
        if fls_id in canonical_ids:
            result["valid_count"] += 1
        else:
            # Check if this might be a null-mapped section (unmapped in FLS source)
            # These are OK - the FLS source just doesn't have an anchor for them
            result["invalid_ids"].append((fls_id, json_path))

    # Count how many sections in the mapping have null fls_id
    def count_null_ids(sections: Dict) -> int:
        count = 0
        for section in sections.values():
            if isinstance(section, dict):
                if section.get("fls_id") is None:
                    count += 1
                count += count_null_ids(section.get("subsections", {}))
        return count

    result["unmapped_in_fls"] = count_null_ids(mapping_sections)

    return result


def validate_section_hierarchy(data: Dict) -> List[str]:
    """
    Validate that fls_section values form a valid hierarchy.

    Checks:
        - Section numbers are well-formed (X.Y.Z pattern, allowing negative components)
        - Child sections are proper children of parents (13.2.1 is child of 13.2)

    FLS Section Number Encoding:
        For FLS content that doesn't have traditional section headings, we use
        a special encoding with negative numbers:
        
        - X.Y     = Standard sections (e.g., 8.1 Let Statements)
        - X.0.Y   = Syntax block productions
        - X.-1.Y  = Top-level unsorted items (items before first heading)
        - X.-2.Y  = Legality rules (e.g., 8.-2.1 Item Statement legality rule)
        - X.-3.Y  = Dynamic semantics (e.g., 8.-3.1 Empty Statement Execution)
        
        This encoding allows us to reference and track FLS content that exists
        outside the traditional section hierarchy, particularly legality rules
        and dynamic semantics which are critical for safety certification.

    Returns list of error messages.
    """
    errors = []
    # Allow negative section components for the special encoding scheme
    section_pattern = re.compile(r"^\d+(\.-?\d+)*$")

    def validate_sections(sections: Dict, parent_section: str = "", path: str = ""):
        for key, section in sections.items():
            if not isinstance(section, dict):
                continue

            current_path = f"{path}.{key}" if path else key
            fls_section = section.get("fls_section", "")

            if fls_section:
                # Check well-formed pattern
                if not section_pattern.match(fls_section):
                    errors.append(
                        f"{current_path}: Invalid section number format: '{fls_section}'"
                    )

                # Check parent-child relationship
                if parent_section:
                    if not fls_section.startswith(parent_section + "."):
                        errors.append(
                            f"{current_path}: Section '{fls_section}' is not a child of '{parent_section}'"
                        )

            # Recurse into subsections
            subsections = section.get("subsections", {})
            if subsections:
                validate_sections(subsections, fls_section, current_path)

    json_sections = data.get("sections", {})
    chapter_num = data.get("chapter", 0)
    validate_sections(json_sections, str(chapter_num) if chapter_num else "")

    return errors


def validate_file(
    file_path: Path, schema: Dict, fls_mapping: Dict, max_depth: Optional[int] = None
) -> Dict:
    """
    Validate a single JSON file.

    Returns dict with:
        - valid: bool (True if no fatal errors)
        - schema_errors: list of schema errors
        - must_be_filled: list of MUST_BE_FILLED locations
        - path_errors: list of invalid sample paths
        - coverage: coverage validation results
        - id_validation: FLS ID validation results
        - hierarchy_errors: section hierarchy errors
    """
    result = {
        "file": file_path.name,
        "valid": True,
        "schema_valid": True,
        "coverage_valid": True,
        "ids_valid": True,
        "schema_errors": [],
        "must_be_filled": [],
        "path_errors": [],
        "coverage": {},
        "id_validation": {},
        "hierarchy_errors": [],
    }

    # Load JSON
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result["valid"] = False
        result["schema_valid"] = False
        result["schema_errors"].append(f"Invalid JSON: {e}")
        return result

    # Schema validation
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        result["valid"] = False
        result["schema_valid"] = False
        result["schema_errors"].append(f"{e.json_path}: {e.message}")
    except jsonschema.SchemaError as e:
        result["valid"] = False
        result["schema_valid"] = False
        result["schema_errors"].append(f"Schema error: {e.message}")

    # Find MUST_BE_FILLED markers
    result["must_be_filled"] = find_must_be_filled(data)

    # Validate sample paths
    samples = find_sample_paths(data)
    version = data.get("version", "0.8.0")
    result["path_errors"] = validate_sample_paths(samples, version)

    # Get chapter number and corresponding mapping
    chapter_num = data.get("chapter", 0)
    chapter_mapping = fls_mapping.get(str(chapter_num), {})

    if chapter_mapping:
        # FLS coverage validation
        result["coverage"] = validate_fls_coverage(data, chapter_mapping, max_depth)
        if result["coverage"]["missing_sections"]:
            result["valid"] = False
            result["coverage_valid"] = False

        # FLS ID validation
        result["id_validation"] = validate_fls_ids(data, chapter_mapping)
        if result["id_validation"]["invalid_ids"]:
            result["valid"] = False
            result["ids_valid"] = False

        # Section hierarchy validation
        result["hierarchy_errors"] = validate_section_hierarchy(data)
        if result["hierarchy_errors"]:
            result["valid"] = False

    return result


def get_missing_chapters(fls_mapping: Dict, existing_files: List[Path]) -> List[Dict]:
    """
    Find chapters in the FLS mapping that don't have corresponding JSON files.

    Returns list of dicts with chapter info.
    """
    missing = []

    # Extract chapter numbers from existing files
    existing_chapters = set()
    for f in existing_files:
        match = re.search(r"fls_chapter(\d+)", f.name)
        if match:
            existing_chapters.add(int(match.group(1)))

    for chapter_num_str, chapter_data in fls_mapping.items():
        chapter_num = int(chapter_num_str)
        if chapter_num not in existing_chapters:
            missing.append(
                {
                    "chapter": chapter_num,
                    "title": chapter_data.get("title", "Unknown"),
                }
            )

    return sorted(missing, key=lambda x: x["chapter"])


def generate_report(
    results: List[Dict], missing_chapters: List[Dict], max_depth: Optional[int]
) -> str:
    """Generate a validation report."""
    lines = []
    lines.append("=" * 60)
    lines.append("FLS MAPPING VALIDATION REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Summary stats
    total_files = len(results)
    schema_valid = sum(1 for r in results if r["schema_valid"])
    coverage_valid = sum(1 for r in results if r["coverage_valid"])
    ids_valid = sum(1 for r in results if r["ids_valid"])
    total_must_fill = sum(len(r["must_be_filled"]) for r in results)
    total_path_errors = sum(len(r["path_errors"]) for r in results)

    lines.append(f"Files validated: {total_files}")
    lines.append(f"Schema valid: {schema_valid}/{total_files}")
    lines.append(f"Coverage valid: {coverage_valid}/{total_files}")
    lines.append(f"FLS IDs valid: {ids_valid}/{total_files}")
    lines.append(f"MUST_BE_FILLED markers: {total_must_fill}")
    lines.append(f"Path errors: {total_path_errors}")
    if max_depth:
        lines.append(f"Coverage depth limit: {max_depth}")
    lines.append("")

    # Per-file details
    for result in results:
        lines.append("-" * 60)
        lines.append(f"FILE: {result['file']}")
        lines.append("-" * 60)

        if result["schema_errors"]:
            lines.append("  SCHEMA ERRORS:")
            for err in result["schema_errors"]:
                lines.append(f"    - {err}")

        if result["must_be_filled"]:
            lines.append(f"  MUST_BE_FILLED ({len(result['must_be_filled'])}):")
            for path in result["must_be_filled"][:10]:
                lines.append(f"    - {path}")
            if len(result["must_be_filled"]) > 10:
                lines.append(f"    ... and {len(result['must_be_filled']) - 10} more")

        if result["path_errors"]:
            lines.append(f"  PATH ERRORS ({len(result['path_errors'])}):")
            for err in result["path_errors"][:5]:
                lines.append(f"    - {err}")
            if len(result["path_errors"]) > 5:
                lines.append(f"    ... and {len(result['path_errors']) - 5} more")

        if result["hierarchy_errors"]:
            lines.append(f"  HIERARCHY ERRORS ({len(result['hierarchy_errors'])}):")
            for err in result["hierarchy_errors"][:5]:
                lines.append(f"    - {err}")
            if len(result["hierarchy_errors"]) > 5:
                lines.append(
                    f"    ... and {len(result['hierarchy_errors']) - 5} more"
                )

        if (
            not result["schema_errors"]
            and not result["must_be_filled"]
            and not result["path_errors"]
            and not result["hierarchy_errors"]
            and result["coverage_valid"]
            and result["ids_valid"]
        ):
            lines.append("  OK - No issues found")

        lines.append("")

    # FLS Coverage Report
    lines.append("=" * 60)
    lines.append("FLS COVERAGE REPORT")
    lines.append("=" * 60)

    for result in results:
        coverage = result.get("coverage", {})
        if not coverage:
            continue

        lines.append(f"\n{result['file']}:")
        total = coverage.get("total_expected", 0)
        found = coverage.get("total_found", 0)
        pct = coverage.get("coverage_percent", 0)
        lines.append(f"  Coverage: {found}/{total} sections ({pct:.0f}%)")

        missing = coverage.get("missing_sections", [])
        if missing:
            lines.append("  Missing:")
            for fls_section, title in missing[:10]:
                lines.append(f"    - {fls_section} {title}")
            if len(missing) > 10:
                lines.append(f"    ... and {len(missing) - 10} more")
        else:
            lines.append("  Missing: none")

        extra = coverage.get("extra_sections", [])
        if extra:
            lines.append("  Extra (informational):")
            for section in extra[:10]:
                lines.append(f"    - {section}")
            if len(extra) > 10:
                lines.append(f"    ... and {len(extra) - 10} more")

    # FLS ID Validation Report
    lines.append("")
    lines.append("=" * 60)
    lines.append("FLS ID VALIDATION")
    lines.append("=" * 60)

    for result in results:
        id_validation = result.get("id_validation", {})
        if not id_validation:
            continue

        lines.append(f"\n{result['file']}:")
        valid = id_validation.get("valid_count", 0)
        invalid = id_validation.get("invalid_ids", [])
        unmapped = id_validation.get("unmapped_in_fls", 0)

        lines.append(f"  Valid IDs: {valid}")

        if invalid:
            lines.append(f"  Invalid IDs ({len(invalid)}):")
            for fls_id, path in invalid[:5]:
                lines.append(f"    - {fls_id} (at {path})")
            if len(invalid) > 5:
                lines.append(f"    ... and {len(invalid) - 5} more")
        else:
            lines.append("  Invalid IDs: none")

        syntax_extracted = id_validation.get("syntax_extracted", 0)
        if syntax_extracted:
            lines.append(f"  Extracted from syntax (no native ID): {syntax_extracted} (OK)")

        if unmapped:
            lines.append(f"  Unmapped in FLS source: {unmapped} (OK)")

    # Missing Chapters Report
    if missing_chapters:
        lines.append("")
        lines.append("=" * 60)
        lines.append("MISSING CHAPTERS")
        lines.append("=" * 60)

        for chapter in missing_chapters:
            lines.append(
                f"\n  Chapter {chapter['chapter']} ({chapter['title']}): No JSON file found"
            )

    # MUST_BE_FILLED Inventory
    lines.append("")
    lines.append("=" * 60)
    lines.append("MUST_BE_FILLED INVENTORY")
    lines.append("=" * 60)

    has_must_fill = False
    for result in results:
        if result["must_be_filled"]:
            has_must_fill = True
            lines.append(f"\n{result['file']}:")
            for path in result["must_be_filled"]:
                lines.append(f"  - {path}")

    if not has_must_fill:
        lines.append("\n  (none)")

    # Exit codes reference
    lines.append("")
    lines.append("=" * 60)
    lines.append("EXIT CODES")
    lines.append("=" * 60)
    lines.append("  0 = All checks pass")
    lines.append("  1 = Schema validation failed")
    lines.append("  2 = FLS coverage check failed")
    lines.append("  3 = FLS ID validation failed")
    lines.append("  4 = Multiple failures")

    return "\n".join(lines)


def calculate_exit_code(results: List[Dict]) -> int:
    """
    Calculate the appropriate exit code based on validation results.

    Returns:
        0 - All checks pass
        1 - Schema validation failed
        2 - FLS coverage check failed
        3 - FLS ID validation failed
        4 - Multiple failures
    """
    schema_failed = any(not r["schema_valid"] for r in results)
    coverage_failed = any(not r["coverage_valid"] for r in results)
    ids_failed = any(not r["ids_valid"] for r in results)

    failures = sum([schema_failed, coverage_failed, ids_failed])

    if failures == 0:
        return 0
    elif failures > 1:
        return 4
    elif schema_failed:
        return 1
    elif coverage_failed:
        return 2
    else:  # ids_failed
        return 3


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Load schema
    if not SCHEMA_PATH.exists():
        print(f"Error: Schema not found at {SCHEMA_PATH}")
        return 1
    schema = load_schema()

    # Load FLS mapping
    if not FLS_MAPPING_PATH.exists():
        print(f"Error: FLS mapping not found at {FLS_MAPPING_PATH}")
        return 1
    fls_mapping = load_fls_mapping()

    # Find JSON files to validate
    if args.file:
        target_file = MAPPING_DIR / args.file
        if not target_file.exists():
            print(f"Error: File not found: {target_file}")
            return 1
        json_files = [target_file]
    else:
        json_files = sorted(MAPPING_DIR.glob("fls_chapter*.json"))

    if not json_files:
        print("No FLS mapping files found.")
        return 1

    print(f"Validating {len(json_files)} files...")
    if args.depth:
        print(f"Coverage depth limit: {args.depth}")

    results = []
    for json_file in json_files:
        print(f"  Checking {json_file.name}...")
        result = validate_file(json_file, schema, fls_mapping, args.depth)
        results.append(result)

    # Find missing chapters
    missing_chapters = get_missing_chapters(fls_mapping, json_files)

    # Generate report
    report = generate_report(results, missing_chapters, args.depth)
    print("\n" + report)

    # Write report to file
    report_path = ROOT_DIR / "validation_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    # Return exit code
    return calculate_exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
