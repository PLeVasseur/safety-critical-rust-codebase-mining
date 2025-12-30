#!/usr/bin/env -S uv run python
"""
Validate coding standards JSON files against their schemas.

This script validates:
1. Standards files (MISRA/CERT rule listings) against coding_standard_rules.schema.json
2. Mapping files (FLS mappings) against fls_mapping.schema.json
3. FLS ID references against the canonical FLS section mapping

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

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
STANDARDS_DIR = ROOT_DIR / "coding-standards-fls-mapping" / "standards"
MAPPINGS_DIR = ROOT_DIR / "coding-standards-fls-mapping" / "mappings"
SCHEMA_DIR = ROOT_DIR / "coding-standards-fls-mapping" / "schema"
FLS_MAPPING_PATH = SCRIPT_DIR / "fls_section_mapping.json"

# Schema file names
RULES_SCHEMA = "coding_standard_rules.schema.json"
MAPPING_SCHEMA = "fls_mapping.schema.json"


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def load_fls_ids() -> set[str]:
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
                # Skip synthetic IDs
                if not obj["fls_id"].startswith("fls_extracted"):
                    fls_ids.add(obj["fls_id"])
            for value in obj.values():
                extract_ids(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_ids(item)

    extract_ids(fls_data)
    return fls_ids


def validate_schema(data: dict, schema: dict, filename: str) -> list[str]:
    """Validate data against a JSON schema. Returns list of errors."""
    errors = []
    validator = jsonschema.Draft202012Validator(schema)

    for error in validator.iter_errors(data):
        path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
        errors.append(f"{filename}: {path}: {error.message}")

    return errors


def validate_fls_ids(data: dict, valid_fls_ids: set[str], filename: str) -> list[str]:
    """Validate that all FLS IDs in a mapping file are valid."""
    errors = []

    if "mappings" not in data:
        return errors

    for mapping in data["mappings"]:
        guideline_id = mapping.get("guideline_id", "unknown")
        fls_ids = mapping.get("fls_ids", [])

        for fls_id in fls_ids:
            if fls_id not in valid_fls_ids:
                errors.append(f"{filename}: {guideline_id}: Unknown FLS ID '{fls_id}'")

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

    # Compute statistics
    mappings = data.get("mappings", [])
    stats = {
        "standard": data.get("standard", "unknown"),
        "total": len(mappings),
        "mapped": sum(1 for m in mappings if m.get("applicability") in ("direct", "partial")),
        "unmapped": sum(1 for m in mappings if m.get("applicability") == "unmapped"),
        "not_applicable": sum(
            1 for m in mappings
            if m.get("applicability") in ("not_applicable", "rust_prevents")
        ),
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

    # Load valid FLS IDs
    valid_fls_ids = load_fls_ids()
    print(f"Loaded {len(valid_fls_ids)} valid FLS IDs")

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
                    print(f"    OK - {stats['standard']}")
                    print(
                        f"       {stats['mapped']} mapped, "
                        f"{stats['unmapped']} unmapped, "
                        f"{stats['not_applicable']} N/A"
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
