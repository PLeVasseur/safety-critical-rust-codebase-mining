#!/usr/bin/env python3
"""
validate_decisions.py - Validate decision files in a decisions directory.

This tool validates individual guideline verification decision files used in the
parallel verification workflow. Supports both v1 and v2 decision file formats.

Validation checks:
1. Schema validation against decision_file.schema.json (v1 or v2)
2. Filename-to-guideline_id consistency (Dir_1.1.json should contain "Dir 1.1")
3. No duplicate guideline_ids across files
4. FLS ID format validity
5. Non-empty reason fields on matches
6. If --batch-report provided: verify guideline_ids exist in batch
7. v2-specific: per-context progress reporting

Usage:
    uv run validate-decisions \\
        --decisions-dir cache/verification/misra-c/batch4_decisions/

    uv run validate-decisions \\
        --decisions-dir cache/verification/misra-c/batch4_decisions/ \\
        --batch-report cache/verification/misra-c/batch4_session6.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema

from fls_tools.shared import get_project_root, get_coding_standards_dir


def load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return None


def load_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        print(f"WARNING: Decision file schema not found: {schema_path}", file=sys.stderr)
        return None
    return load_json(schema_path)


def guideline_id_to_filename(guideline_id: str) -> str:
    """Convert guideline ID to expected filename."""
    return guideline_id.replace(" ", "_") + ".json"


def filename_to_guideline_id(filename: str) -> str:
    """Convert filename back to guideline ID."""
    # Remove .json extension and replace underscores with spaces
    base = filename.rsplit(".json", 1)[0]
    return base.replace("_", " ")


def validate_decision_file(
    path: Path,
    schema: dict | None,
    batch_guideline_ids: set[str] | None = None,
) -> tuple[bool, list[str], dict | None]:
    """
    Validate a single decision file.
    
    Returns:
        (is_valid, errors, parsed_data)
    """
    errors = []
    
    # Load file
    data = load_json(path)
    if data is None:
        errors.append(f"Failed to parse JSON")
        return False, errors, None
    
    # Schema validation
    if schema:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema error: {e.message}")
            if e.path:
                errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
    
    # Filename consistency
    expected_filename = guideline_id_to_filename(data.get("guideline_id", ""))
    if path.name != expected_filename:
        errors.append(
            f"Filename mismatch: file is '{path.name}' but guideline_id suggests '{expected_filename}'"
        )
    
    # Check guideline exists in batch report
    if batch_guideline_ids is not None:
        gid = data.get("guideline_id")
        if gid and gid not in batch_guideline_ids:
            errors.append(f"Guideline '{gid}' not found in batch report")
    
    # Detect schema version
    schema_version = data.get("schema_version", "1.0")
    
    # Validate FLS IDs format - handle v1 and v2 structures
    fls_id_pattern = re.compile(r"^fls_[a-zA-Z0-9]+$")
    
    def validate_matches(matches: list, prefix: str) -> None:
        """Validate FLS matches in a list."""
        for i, match in enumerate(matches):
            fls_id = match.get("fls_id", "")
            if not fls_id_pattern.match(fls_id):
                errors.append(f"{prefix}[{i}]: Invalid fls_id format '{fls_id}'")
            
            reason = match.get("reason", "")
            if not reason or not reason.strip():
                errors.append(f"{prefix}[{i}]: Empty reason field")
    
    if schema_version == "2.0":
        # v2: validate each context
        for context in ["all_rust", "safe_rust"]:
            ctx_data = data.get(context, {})
            validate_matches(ctx_data.get("accepted_matches", []), f"{context}.accepted_matches")
            validate_matches(ctx_data.get("rejected_matches", []), f"{context}.rejected_matches")
    else:
        # v1: flat structure
        validate_matches(data.get("accepted_matches", []), "accepted_matches")
        validate_matches(data.get("rejected_matches", []), "rejected_matches")
    
    is_valid = len(errors) == 0
    return is_valid, errors, data


def validate_decisions_directory(
    decisions_dir: Path,
    schema: dict | None,
    batch_report_path: Path | None = None,
) -> dict:
    """
    Validate all decision files in a directory.
    
    Returns dict with:
        valid_count, invalid_count, errors_by_file, guideline_ids,
        v2 per-context stats: all_rust_decided, safe_rust_decided, both_decided
    """
    # Load batch report for cross-reference if provided
    batch_guideline_ids = None
    if batch_report_path and batch_report_path.exists():
        batch_report = load_json(batch_report_path)
        if batch_report:
            batch_guideline_ids = {
                g["guideline_id"] for g in batch_report.get("guidelines", [])
            }
    
    # Find all decision files
    decision_files = sorted(decisions_dir.glob("*.json"))
    
    valid_count = 0
    invalid_count = 0
    errors_by_file = []
    all_guideline_ids = set()
    guideline_id_to_file = {}
    
    # v2 per-context tracking
    all_rust_decided = set()
    safe_rust_decided = set()
    both_decided = set()
    v1_count = 0
    v2_count = 0
    
    for path in decision_files:
        is_valid, errors, data = validate_decision_file(path, schema, batch_guideline_ids)
        
        if data:
            gid = data.get("guideline_id")
            schema_version = data.get("schema_version", "1.0")
            
            if gid:
                # Check for duplicates
                if gid in all_guideline_ids:
                    errors.append(
                        f"Duplicate guideline_id '{gid}' - also in {guideline_id_to_file[gid]}"
                    )
                    is_valid = False
                else:
                    all_guideline_ids.add(gid)
                    guideline_id_to_file[gid] = path.name
                
                # Track per-context decisions
                if schema_version == "2.0":
                    v2_count += 1
                    ar = data.get("all_rust", {})
                    sr = data.get("safe_rust", {})
                    
                    if ar.get("decision"):
                        all_rust_decided.add(gid)
                    if sr.get("decision"):
                        safe_rust_decided.add(gid)
                    if ar.get("decision") and sr.get("decision"):
                        both_decided.add(gid)
                else:
                    v1_count += 1
                    # v1: single decision applies to both
                    if data.get("decision"):
                        all_rust_decided.add(gid)
                        safe_rust_decided.add(gid)
                        both_decided.add(gid)
        
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1
            errors_by_file.append((path.name, errors))
    
    return {
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "errors_by_file": errors_by_file,
        "guideline_ids": all_guideline_ids,
        "all_rust_decided": all_rust_decided,
        "safe_rust_decided": safe_rust_decided,
        "both_decided": both_decided,
        "v1_count": v1_count,
        "v2_count": v2_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate decision files in a decisions directory"
    )
    parser.add_argument(
        "--decisions-dir",
        type=str,
        required=True,
        help="Path to the decisions directory",
    )
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to batch report for cross-reference validation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show details for valid files too",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Resolve paths
    decisions_dir = Path(args.decisions_dir)
    if not decisions_dir.is_absolute():
        decisions_dir = root / decisions_dir
    
    batch_report_path = None
    if args.batch_report:
        batch_report_path = Path(args.batch_report)
        if not batch_report_path.is_absolute():
            batch_report_path = root / batch_report_path
    
    # Check directory exists
    if not decisions_dir.exists():
        print(f"ERROR: Decisions directory not found: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    if not decisions_dir.is_dir():
        print(f"ERROR: Not a directory: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Load schema
    schema = load_schema(root)
    
    # Validate
    print(f"Validating decisions in {decisions_dir}")
    print()
    
    result = validate_decisions_directory(decisions_dir, schema, batch_report_path)
    
    valid_count = result["valid_count"]
    invalid_count = result["invalid_count"]
    errors_by_file = result["errors_by_file"]
    guideline_ids = result["guideline_ids"]
    total_count = valid_count + invalid_count
    
    if total_count == 0:
        print("No decision files found.")
        sys.exit(0)
    
    # Print results
    print(f"Found {total_count} decision files")
    print(f"  v1 format: {result['v1_count']}")
    print(f"  v2 format: {result['v2_count']}")
    print()
    
    # Per-context progress (v2)
    if result["v2_count"] > 0:
        print("Per-context progress:")
        print(f"  all_rust decided:  {len(result['all_rust_decided'])}/{total_count}")
        print(f"  safe_rust decided: {len(result['safe_rust_decided'])}/{total_count}")
        print(f"  Both decided:      {len(result['both_decided'])}/{total_count}")
        print()
    
    if errors_by_file:
        print("Validation errors:")
        for filename, errors in errors_by_file:
            print(f"  {filename}:")
            for error in errors:
                print(f"    - {error}")
        print()
    
    # Cross-reference with batch report
    if batch_report_path and batch_report_path.exists():
        batch_report = load_json(batch_report_path)
        if batch_report:
            batch_guidelines = {g["guideline_id"] for g in batch_report.get("guidelines", [])}
            missing = batch_guidelines - guideline_ids
            extra = guideline_ids - batch_guidelines
            
            print("Cross-reference with batch report:")
            print(f"  Batch guidelines: {len(batch_guidelines)}")
            print(f"  Decisions found: {len(guideline_ids)}")
            print(f"  Coverage: {len(guideline_ids)}/{len(batch_guidelines)} ({100*len(guideline_ids)/len(batch_guidelines):.0f}%)")
            if missing:
                print(f"  Pending: {len(missing)} guidelines")
                if len(missing) <= 10:
                    print(f"    {', '.join(sorted(missing))}")
            if extra:
                print(f"  Extra (not in batch): {len(extra)}")
            print()
    
    # Summary
    print("Summary:")
    print(f"  Valid: {valid_count}/{total_count}")
    print(f"  Invalid: {invalid_count}/{total_count}")
    
    if invalid_count > 0:
        print()
        print("Validation FAILED")
        sys.exit(1)
    else:
        print()
        print("Validation PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
