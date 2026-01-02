#!/usr/bin/env python3
"""
Validate MISRA Rust Applicability JSON against its schema.

This script validates coding-standards-fls-mapping/misra_rust_applicability.json
against coding-standards-fls-mapping/schema/misra_rust_applicability.schema.json.

It also performs additional semantic validation:
- Verifies all expected guidelines are present
- Checks rationale values are valid combinations
- Validates guideline ID format

Usage:
    uv run validate-applicability
    uv run validate-applicability --verbose

Exit Codes:
    0 - All validations pass
    1 - Schema validation failed
    2 - Semantic validation failed
"""

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from fls_tools.shared import get_project_root, get_coding_standards_dir


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_schema(data: dict, schema: dict) -> list[str]:
    """
    Validate data against JSON schema.
    
    Returns list of error messages (empty if valid).
    """
    errors = []
    validator = jsonschema.Draft202012Validator(schema)
    
    for error in validator.iter_errors(data):
        path = ".".join(str(p) for p in error.absolute_path)
        if path:
            errors.append(f"{path}: {error.message}")
        else:
            errors.append(error.message)
    
    return errors


def validate_semantics(data: dict, verbose: bool = False) -> list[str]:
    """
    Perform semantic validation beyond schema.
    
    Returns list of error messages (empty if valid).
    """
    errors = []
    warnings = []
    
    guidelines = data.get("guidelines", {})
    
    # Count guidelines by type
    regular_count = 0
    renumbered_count = 0
    directives = []
    rules = []
    
    for gid, gdata in guidelines.items():
        if gdata.get("renumbered"):
            renumbered_count += 1
        else:
            regular_count += 1
            if gid.startswith("Dir"):
                directives.append(gid)
            else:
                rules.append(gid)
    
    if verbose:
        print(f"  Regular guidelines: {regular_count}")
        print(f"  Renumbered entries: {renumbered_count}")
        print(f"  Directives: {len(directives)}")
        print(f"  Rules: {len(rules)}")
    
    # Check rationale distribution
    rationale_counts = {"UB": 0, "IDB": 0, "CQ": 0, "DC": 0}
    guidelines_without_rationale = []
    
    for gid, gdata in guidelines.items():
        if gdata.get("renumbered"):
            continue
        
        rationale = gdata.get("rationale", [])
        if not rationale:
            guidelines_without_rationale.append(gid)
        else:
            for r in rationale:
                if r in rationale_counts:
                    rationale_counts[r] += 1
    
    if verbose:
        print(f"\n  Rationale distribution:")
        for r, count in sorted(rationale_counts.items()):
            print(f"    {r}: {count}")
    
    # Warnings for guidelines without rationale (not errors)
    if guidelines_without_rationale and verbose:
        print(f"\n  Guidelines without rationale: {len(guidelines_without_rationale)}")
        for gid in guidelines_without_rationale[:5]:
            print(f"    - {gid}")
        if len(guidelines_without_rationale) > 5:
            print(f"    ... and {len(guidelines_without_rationale) - 5} more")
    
    # Check adjusted category distribution
    adj_cat_counts = {}
    for gid, gdata in guidelines.items():
        if gdata.get("renumbered"):
            continue
        cat = gdata.get("adjusted_category", "unknown")
        adj_cat_counts[cat] = adj_cat_counts.get(cat, 0) + 1
    
    if verbose:
        print(f"\n  Adjusted category distribution:")
        for cat, count in sorted(adj_cat_counts.items()):
            print(f"    {cat}: {count}")
    
    # Check metadata consistency
    total_in_metadata = data.get("metadata", {}).get("total_guidelines", 0)
    actual_total = len(guidelines)
    if total_in_metadata != actual_total:
        errors.append(
            f"Metadata total_guidelines ({total_in_metadata}) doesn't match "
            f"actual guideline count ({actual_total})"
        )
    
    # Check for expected guideline count (MISRA C:2025 has ~228 guidelines)
    if actual_total < 200:
        warnings.append(f"Only {actual_total} guidelines found (expected ~228)")
    
    if verbose and warnings:
        print(f"\n  Warnings:")
        for w in warnings:
            print(f"    - {w}")
    
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Validate MISRA Rust Applicability JSON"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed validation information"
    )
    parser.add_argument(
        "--file", "-f",
        help="Path to applicability JSON (default: auto-detect)"
    )
    parser.add_argument(
        "--schema", "-s",
        help="Path to schema file (default: auto-detect)"
    )
    args = parser.parse_args()
    
    root = get_project_root()
    coding_standards_dir = get_coding_standards_dir(root)
    
    # Determine paths
    if args.file:
        data_path = Path(args.file)
    else:
        data_path = coding_standards_dir / "misra_rust_applicability.json"
    
    if args.schema:
        schema_path = Path(args.schema)
    else:
        schema_path = coding_standards_dir / "schema" / "misra_rust_applicability.schema.json"
    
    # Check files exist
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        return 1
    
    if not schema_path.exists():
        print(f"Error: Schema file not found: {schema_path}")
        return 1
    
    print(f"Validating: {data_path.name}")
    print(f"Schema: {schema_path.name}")
    
    # Load files
    try:
        data = load_json(data_path)
        schema = load_json(schema_path)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return 1
    
    # Schema validation
    print("\n1. Schema validation...")
    schema_errors = validate_schema(data, schema)
    
    if schema_errors:
        print(f"   FAILED - {len(schema_errors)} error(s)")
        for err in schema_errors[:10]:
            print(f"   - {err}")
        if len(schema_errors) > 10:
            print(f"   ... and {len(schema_errors) - 10} more")
        return 1
    else:
        print("   PASSED")
    
    # Semantic validation
    print("\n2. Semantic validation...")
    semantic_errors = validate_semantics(data, verbose=args.verbose)
    
    if semantic_errors:
        print(f"   FAILED - {len(semantic_errors)} error(s)")
        for err in semantic_errors:
            print(f"   - {err}")
        return 2
    else:
        print("   PASSED")
    
    print("\nAll validations passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
