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

from fls_tools.shared import get_project_root, get_coding_standards_dir, get_tools_dir

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
    
    Checks FLS IDs in:
    - fls_ids array
    - accepted_matches array (fls_id field)
    - rejected_matches array (fls_id field)
    """
    errors = []

    if "mappings" not in data:
        return errors

    for mapping in data["mappings"]:
        guideline_id = mapping.get("guideline_id", "unknown")
        
        # Check fls_ids array
        fls_ids = mapping.get("fls_ids", [])
        for fls_id in fls_ids:
            if fls_id not in valid_fls_ids:
                errors.append(f"{filename}: {guideline_id}: Unknown FLS ID '{fls_id}' in fls_ids")
        
        # Check accepted_matches array
        accepted_matches = mapping.get("accepted_matches", [])
        for match in accepted_matches:
            fls_id = match.get("fls_id")
            if fls_id and fls_id not in valid_fls_ids:
                errors.append(f"{filename}: {guideline_id}: Unknown FLS ID '{fls_id}' in accepted_matches")
        
        # Check rejected_matches array
        rejected_matches = mapping.get("rejected_matches", [])
        for match in rejected_matches:
            fls_id = match.get("fls_id")
            if fls_id and fls_id not in valid_fls_ids:
                errors.append(f"{filename}: {guideline_id}: Unknown FLS ID '{fls_id}' in rejected_matches")

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
) -> tuple[list[str], dict]:
    """Validate a mapping file and return errors and statistics."""
    data = load_json(filepath)
    errors = validate_schema(data, schema, filepath.name)

    # Validate FLS IDs
    fls_errors = validate_fls_ids(data, valid_fls_ids, filepath.name)
    errors.extend(fls_errors)

    # Compute statistics for both applicability dimensions
    mappings = data.get("mappings", [])
    
    def count_applicability(field: str) -> dict[str, int]:
        """Count applicability values for a given field."""
        return {
            "direct": sum(1 for m in mappings if m.get(field) == "direct"),
            "partial": sum(1 for m in mappings if m.get(field) == "partial"),
            "not_applicable": sum(1 for m in mappings if m.get(field) == "not_applicable"),
            "rust_prevents": sum(1 for m in mappings if m.get(field) == "rust_prevents"),
            "unmapped": sum(1 for m in mappings if m.get(field) == "unmapped"),
        }
    
    stats = {
        "standard": data.get("standard", "unknown"),
        "total": len(mappings),
        "all_rust": count_applicability("applicability_all_rust"),
        "safe_rust": count_applicability("applicability_safe_rust"),
    }

    return errors, stats


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
            for filepath in sorted(mapping_files):
                print(f"\n  {filepath.name}:")
                errors, stats = validate_mapping_file(filepath, mapping_schema, valid_fls_ids)

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

                if not errors:
                    print(f"    OK - {stats['standard']} ({stats['total']} guidelines)")
                    all_rust = stats["all_rust"]
                    safe_rust = stats["safe_rust"]
                    print(
                        f"       All Rust:  {all_rust['direct']} direct, "
                        f"{all_rust['partial']} partial, "
                        f"{all_rust['not_applicable']} N/A, "
                        f"{all_rust['rust_prevents']} rust_prevents"
                    )
                    print(
                        f"       Safe Rust: {safe_rust['direct']} direct, "
                        f"{safe_rust['partial']} partial, "
                        f"{safe_rust['not_applicable']} N/A, "
                        f"{safe_rust['rust_prevents']} rust_prevents"
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
