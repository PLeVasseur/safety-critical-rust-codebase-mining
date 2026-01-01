#!/usr/bin/env python3
"""
apply_verification.py - Phase 4: Apply Verified Changes

This script applies verified decisions from a batch report to:
- misra_c_to_fls.json: Update accepted/rejected matches and confidence
- verification_progress.json: Mark guidelines as verified

Usage:
    uv run python verification/apply_verification.py \
        --batch-report cache/verification/batch3_session5.json \
        --session 5 \
        --apply-applicability-changes
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_tools_dir,
    get_misra_c_mappings_path,
    get_verification_progress_path,
    get_coding_standards_dir,
    get_batch_report_path,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
)


def load_json(path: Path, description: str) -> dict:
    """Load a JSON file with error handling."""
    if not path.exists():
        print(f"ERROR: {description} not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict, description: str):
    """Save a JSON file with formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Updated {description}: {path}", file=sys.stderr)


def load_batch_report_schema(root: Path) -> dict | None:
    """Load the batch report JSON schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "batch_report.schema.json"
    if not schema_path.exists():
        print(f"WARNING: Batch report schema not found: {schema_path}", file=sys.stderr)
        return None
    with open(schema_path) as f:
        return json.load(f)


def validate_batch_report(report: dict, schema: dict | None = None) -> list[str]:
    """
    Validate that the batch report is ready to apply.
    
    Uses schema validation if schema is provided, plus additional semantic checks.
    """
    errors = []
    
    if not report.get("guidelines"):
        errors.append("No guidelines in batch report")
        return errors
    
    # Schema validation if available
    if schema:
        try:
            jsonschema.validate(instance=report, schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Schema validation error: {e.message}")
            if e.path:
                errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
        except jsonschema.SchemaError as e:
            errors.append(f"Schema error: {e.message}")
    
    # Semantic validation for apply-readiness
    # (verification_decision must be fully populated, not just scaffolded)
    for g in report["guidelines"]:
        gid = g.get("guideline_id", "UNKNOWN")
        decision = g.get("verification_decision")
        
        if decision is None:
            errors.append(f"{gid}: verification_decision is null (not verified)")
        elif not isinstance(decision, dict):
            errors.append(f"{gid}: verification_decision is not an object")
        else:
            # Check that required fields are not just scaffolded (None)
            if decision.get("decision") is None:
                errors.append(f"{gid}: verification_decision.decision is null")
            if decision.get("confidence") is None:
                errors.append(f"{gid}: verification_decision.confidence is null")
            if decision.get("fls_rationale_type") is None:
                errors.append(f"{gid}: verification_decision.fls_rationale_type is null")
            if "accepted_matches" not in decision:
                errors.append(f"{gid}: verification_decision missing 'accepted_matches'")
    
    return errors


def validate_applicability_changes(report: dict, apply_changes: bool) -> list[str]:
    """Validate applicability changes if they will be applied."""
    warnings = []
    
    changes = report.get("applicability_changes", [])
    if not changes:
        return warnings
    
    if apply_changes:
        unapproved = [c for c in changes if c.get("approved") is not True]
        if unapproved:
            for c in unapproved:
                warnings.append(
                    f"{c['guideline_id']}: applicability change not approved "
                    f"({c['field']}: {c['current_value']} -> {c['proposed_value']})"
                )
    
    return warnings


def update_mappings(
    mappings: dict,
    report: dict,
    apply_applicability_changes: bool,
) -> tuple[dict, int]:
    """
    Update mappings with verified decisions.
    
    Returns updated mappings and count of updated guidelines.
    """
    # Build lookup by guideline_id
    mapping_lookup = {m["guideline_id"]: m for m in mappings["mappings"]}
    
    # Build applicability changes lookup
    approved_changes = {}
    if apply_applicability_changes:
        for change in report.get("applicability_changes", []):
            if change.get("approved") is True:
                gid = change["guideline_id"]
                if gid not in approved_changes:
                    approved_changes[gid] = []
                approved_changes[gid].append(change)
    
    updated_count = 0
    
    for g in report["guidelines"]:
        gid = g["guideline_id"]
        decision = g.get("verification_decision")
        
        if decision is None:
            continue
        
        if gid not in mapping_lookup:
            print(f"WARNING: {gid} not found in mappings, skipping", file=sys.stderr)
            continue
        
        mapping = mapping_lookup[gid]
        
        # Update accepted/rejected matches
        mapping["accepted_matches"] = decision.get("accepted_matches", [])
        mapping["rejected_matches"] = decision.get("rejected_matches", [])
        
        # Update confidence
        mapping["confidence"] = decision.get("confidence", "high")
        
        # Update fls_rationale_type
        if decision.get("fls_rationale_type"):
            mapping["fls_rationale_type"] = decision["fls_rationale_type"]
        
        # Update notes if provided
        if decision.get("notes"):
            mapping["notes"] = decision["notes"]
        
        # Apply approved applicability changes
        if gid in approved_changes:
            for change in approved_changes[gid]:
                field = change["field"]
                mapping[field] = change["proposed_value"]
                print(f"  {gid}: Applied {field} = {change['proposed_value']}", file=sys.stderr)
        
        updated_count += 1
    
    return mappings, updated_count


def update_progress(
    progress: dict,
    report: dict,
    session_id: int,
) -> tuple[dict, int]:
    """
    Update verification progress with verified guidelines.
    
    Returns updated progress and count of newly verified guidelines.
    """
    batch_id = report["batch_id"]
    
    # Find the batch
    target_batch = None
    for batch in progress["batches"]:
        if batch["batch_id"] == batch_id:
            target_batch = batch
            break
    
    if not target_batch:
        print(f"ERROR: Batch {batch_id} not found in progress file", file=sys.stderr)
        return progress, 0
    
    # Build guideline lookup within batch
    guideline_lookup = {g["guideline_id"]: g for g in target_batch["guidelines"]}
    
    verified_count = 0
    
    for g in report["guidelines"]:
        gid = g["guideline_id"]
        decision = g.get("verification_decision")
        
        if decision is None:
            continue
        
        if gid not in guideline_lookup:
            print(f"WARNING: {gid} not found in batch {batch_id}, skipping", file=sys.stderr)
            continue
        
        pg = guideline_lookup[gid]
        
        if pg["status"] != "verified":
            pg["status"] = "verified"
            pg["verified"] = True
            pg["session_id"] = session_id
            verified_count += 1
    
    # Update batch status
    all_verified = all(g["status"] == "verified" for g in target_batch["guidelines"])
    if all_verified:
        target_batch["status"] = "completed"
        print(f"Batch {batch_id} marked as completed", file=sys.stderr)
    else:
        target_batch["status"] = "in_progress"
    
    # Update or add session
    session_exists = any(s["session_id"] == session_id for s in progress.get("sessions", []))
    if not session_exists:
        if "sessions" not in progress:
            progress["sessions"] = []
        progress["sessions"].append({
            "session_id": session_id,
            "date": date.today().isoformat(),
            "batch_id": batch_id,
            "guidelines_verified": verified_count,
        })
    else:
        for s in progress["sessions"]:
            if s["session_id"] == session_id:
                s["guidelines_verified"] = s.get("guidelines_verified", 0) + verified_count
                s["date"] = date.today().isoformat()
    
    return progress, verified_count


def run_validation(root: Path) -> bool:
    """Run validation scripts and return success status."""
    import subprocess
    
    print("\nRunning validation...", file=sys.stderr)
    
    try:
        result = subprocess.run(
            ["uv", "run", "validate-standards"],
            cwd=root / "tools",
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            print("Validation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return False
        
        print("Validation passed", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"Warning: Could not run validation: {e}", file=sys.stderr)
        return True  # Don't fail if validation script isn't available


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: Apply verified changes from batch report"
    )
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to the verified batch report JSON (or use --batch and --session)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Batch number (alternative to --batch-report, requires --session)",
    )
    parser.add_argument(
        "--session",
        type=int,
        required=True,
        help="Session ID for this verification run",
    )
    parser.add_argument(
        "--apply-applicability-changes",
        action="store_true",
        help="Apply approved applicability changes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without writing files",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip running validation scripts after applying changes",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Determine batch report path
    if args.batch is not None:
        # Use --batch and --session to construct path
        report_path = get_batch_report_path(root, args.batch, args.session)
    elif args.batch_report is not None:
        # Resolve and validate user-provided path
        try:
            report_path = resolve_path(Path(args.batch_report))
            report_path = validate_path_in_project(report_path, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("ERROR: Either --batch-report or --batch must be provided", file=sys.stderr)
        sys.exit(1)
    
    # Load batch report
    print(f"Loading batch report from {report_path}...", file=sys.stderr)
    report = load_json(report_path, "Batch report")
    
    # Load schema for validation
    schema = load_batch_report_schema(root)
    
    # Validate batch report
    errors = validate_batch_report(report, schema)
    if errors:
        print("ERROR: Batch report validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check applicability changes
    warnings = validate_applicability_changes(report, args.apply_applicability_changes)
    if warnings:
        print("WARNING: Applicability change issues:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)
        if args.apply_applicability_changes:
            print("Unapproved changes will be skipped.", file=sys.stderr)
    
    # Load current files
    mappings_path = get_misra_c_mappings_path(root)
    progress_path = get_verification_progress_path(root)
    
    mappings = load_json(mappings_path, "MISRA C to FLS mappings")
    progress = load_json(progress_path, "Verification progress")
    
    # Apply updates
    print(f"\nApplying changes from batch {report['batch_id']}...", file=sys.stderr)
    
    updated_mappings, mapping_count = update_mappings(
        mappings, report, args.apply_applicability_changes
    )
    updated_progress, progress_count = update_progress(
        progress, report, args.session
    )
    
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Guidelines updated in mappings: {mapping_count}", file=sys.stderr)
    print(f"  Guidelines marked verified: {progress_count}", file=sys.stderr)
    
    approved_changes = [c for c in report.get("applicability_changes", []) if c.get("approved") is True]
    if approved_changes:
        print(f"  Applicability changes applied: {len(approved_changes)}", file=sys.stderr)
    
    if args.dry_run:
        print("\n[DRY RUN] No files were modified.", file=sys.stderr)
        return
    
    # Save updated files
    save_json(mappings_path, updated_mappings, "MISRA C to FLS mappings")
    save_json(progress_path, updated_progress, "Verification progress")
    
    # Run validation
    if not args.skip_validation:
        if not run_validation(root):
            print("\nWARNING: Validation failed. Review changes manually.", file=sys.stderr)
            sys.exit(1)
    
    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    main()
