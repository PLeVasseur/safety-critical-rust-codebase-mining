#!/usr/bin/env python3
"""
apply_verification.py - Phase 4: Apply Verified Changes (Upgrade to v3)

This script applies verified decisions from a v3 batch report to:
- misra_c_to_fls.json: Update to v3 format with per-context decisions + ADD-6
- verification_progress.json: Mark guidelines as verified per-context

**IMPORTANT: This is where schema upgrades happen.**

When applying v3 decisions, entries are upgraded to v3.0 format regardless
of their original version (v1.0, v1.1, v2.0, v2.1).

Usage:
    uv run apply-verification --standard misra-c --batch 1 --session 1
    uv run apply-verification --standard misra-c --batch 1 --session 1 --dry-run
"""

import argparse
import json
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_standard_mappings_path,
    get_verification_progress_path,
    get_coding_standards_dir,
    get_batch_report_path,
    get_misra_rust_applicability_path,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
    VALID_STANDARDS,
    get_guideline_schema_version,
    convert_v1_applicability_to_v2,
    build_misra_add6_block,
    check_add6_mismatch,
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
        f.write("\n")
    print(f"Updated {description}: {path}", file=sys.stderr)


def load_batch_report_schema(root: Path) -> dict | None:
    """Load the batch report JSON schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "batch_report.schema.json"
    if not schema_path.exists():
        return None
    with open(schema_path) as f:
        return json.load(f)


def load_add6_data(root: Path) -> dict:
    """Load ADD-6 data from misra_rust_applicability.json."""
    add6_path = get_misra_rust_applicability_path(root)
    if not add6_path.exists():
        print(f"WARNING: ADD-6 data not found: {add6_path}", file=sys.stderr)
        return {}
    with open(add6_path) as f:
        data = json.load(f)
    return data.get("guidelines", {})


def validate_batch_report(report: dict) -> list[str]:
    """
    Validate that a batch report is ready to apply.
    
    Accepts v2.0, v2.1, or v3.0 batch reports.
    Checks that verification_decision has both contexts with decisions.
    """
    errors = []
    
    schema_version = report.get("schema_version", "1.0")
    if schema_version not in ("2.0", "3.0"):
        errors.append(f"Expected v2.0 or v3.0 batch report, got {schema_version}")
        return errors
    
    if not report.get("guidelines"):
        errors.append("No guidelines in batch report")
        return errors
    
    for g in report["guidelines"]:
        gid = g.get("guideline_id", "UNKNOWN")
        vd = g.get("verification_decision")
        
        if vd is None:
            errors.append(f"{gid}: verification_decision is null")
            continue
        
        # Check both contexts have decisions
        for context in ["all_rust", "safe_rust"]:
            ctx = vd.get(context, {})
            if ctx.get("decision") is None:
                errors.append(f"{gid}: {context}.decision is null")
    
    return errors


def migrate_v1_to_v3_entry(v1_entry: dict, add6_data: dict | None) -> dict:
    """
    Convert a v1.0 or v1.1 mapping entry to v3.0 structure.
    
    The v1 data is split into both contexts as a starting point.
    The actual verified data will be applied on top.
    """
    entry = {
        "schema_version": "3.0",
        "guideline_id": v1_entry["guideline_id"],
        "guideline_title": v1_entry.get("guideline_title", ""),
        "guideline_type": v1_entry.get("guideline_type", "rule"),
        "all_rust": {
            "applicability": convert_v1_applicability_to_v2(v1_entry.get("applicability_all_rust", "direct")),
            "adjusted_category": None,  # Not in v1
            "rationale_type": v1_entry.get("fls_rationale_type"),
            "confidence": v1_entry.get("confidence", "medium"),
            "accepted_matches": deepcopy(v1_entry.get("accepted_matches", [])),
            "rejected_matches": deepcopy(v1_entry.get("rejected_matches", [])),
            "verified": False,
            "verified_by_session": None,
            "notes": v1_entry.get("notes"),
        },
        "safe_rust": {
            "applicability": convert_v1_applicability_to_v2(v1_entry.get("applicability_safe_rust", "direct")),
            "adjusted_category": None,
            "rationale_type": v1_entry.get("fls_rationale_type"),
            "confidence": v1_entry.get("confidence", "medium"),
            "accepted_matches": deepcopy(v1_entry.get("accepted_matches", [])),
            "rejected_matches": deepcopy(v1_entry.get("rejected_matches", [])),
            "verified": False,
            "verified_by_session": None,
            "notes": v1_entry.get("notes"),
        },
    }
    
    # Add ADD-6 block if available
    if add6_data:
        entry["misra_add6"] = build_misra_add6_block(add6_data)
    
    return entry


def migrate_v2_to_v3_entry(v2_entry: dict, add6_data: dict | None) -> dict:
    """
    Convert a v2.0 or v2.1 mapping entry to v3.0 structure.
    
    Preserves the existing per-context structure and adds/updates misra_add6.
    """
    entry = deepcopy(v2_entry)
    entry["schema_version"] = "3.0"
    
    # Add or update ADD-6 block
    if add6_data:
        entry["misra_add6"] = build_misra_add6_block(add6_data)
    
    return entry


def apply_v2_decision_to_context(
    entry: dict,
    context: str,
    decision: dict,
    session_id: int,
) -> None:
    """
    Apply a v2 context decision to a v2 entry.
    
    Modifies entry in place.
    """
    ctx = entry.get(context, {})
    
    # Apply all decision fields
    ctx["applicability"] = decision.get("applicability")
    ctx["adjusted_category"] = decision.get("adjusted_category")
    ctx["rationale_type"] = decision.get("rationale_type")
    ctx["confidence"] = decision.get("confidence", "high")
    ctx["accepted_matches"] = decision.get("accepted_matches", [])
    ctx["rejected_matches"] = decision.get("rejected_matches", [])
    ctx["notes"] = decision.get("notes")
    ctx["verified"] = True
    ctx["verified_by_session"] = session_id
    
    entry[context] = ctx


def update_mappings_to_v3(
    mappings: dict,
    report: dict,
    session_id: int,
    apply_applicability_changes: bool,
    add6_all: dict,
) -> tuple[dict, int, dict]:
    """
    Update mappings with decisions, upgrading all entries to v3.0.
    
    Returns:
        (updated_mappings, guidelines_updated, upgrade_stats)
    
    upgrade_stats is a dict with keys like "v1.0→v3.0", "v1.1→v3.0", etc.
    """
    # Build lookup by guideline_id
    mapping_lookup = {m["guideline_id"]: (i, m) for i, m in enumerate(mappings["mappings"])}
    
    # Build approved changes lookup
    approved_changes = {}
    if apply_applicability_changes:
        for change in report.get("applicability_changes", []):
            if change.get("approved") is True:
                gid = change["guideline_id"]
                ctx = change.get("context", "all_rust")
                if gid not in approved_changes:
                    approved_changes[gid] = {}
                if ctx not in approved_changes[gid]:
                    approved_changes[gid][ctx] = []
                approved_changes[gid][ctx].append(change)
    
    updated_count = 0
    upgrade_stats = {
        "v1.0→v3.0": 0,
        "v1.1→v3.0": 0,
        "v2.0→v3.0": 0,
        "v2.1→v3.0": 0,
        "v3.0 updated": 0,
    }
    add6_mismatches = []
    
    for g in report["guidelines"]:
        gid = g["guideline_id"]
        vd = g.get("verification_decision")
        
        if vd is None:
            continue
        
        if gid not in mapping_lookup:
            print(f"WARNING: {gid} not found in mappings, skipping", file=sys.stderr)
            continue
        
        idx, existing = mapping_lookup[gid]
        existing_version = get_guideline_schema_version(existing)
        add6_data = add6_all.get(gid)
        
        # Migrate to v3.0 based on existing version
        if existing_version in ("1.0", "1.1"):
            entry = migrate_v1_to_v3_entry(existing, add6_data)
            upgrade_stats[f"{existing_version}→v3.0"] += 1
        elif existing_version in ("2.0", "2.1"):
            entry = migrate_v2_to_v3_entry(existing, add6_data)
            upgrade_stats[f"{existing_version}→v3.0"] += 1
        else:
            # Already v3.0
            entry = deepcopy(existing)
            # Ensure ADD-6 block is present/updated
            if add6_data:
                entry["misra_add6"] = build_misra_add6_block(add6_data)
            upgrade_stats["v3.0 updated"] += 1
        
        # Check for ADD-6 mismatch if batch report has misra_add6
        batch_add6 = g.get("misra_add6")
        if batch_add6 and add6_data:
            mismatches = check_add6_mismatch(batch_add6, add6_data)
            if mismatches:
                add6_mismatches.append((gid, mismatches))
        
        # Apply decisions to each context
        for context in ["all_rust", "safe_rust"]:
            ctx_decision = vd.get(context, {})
            if ctx_decision.get("decision") is not None:
                apply_v2_decision_to_context(entry, context, ctx_decision, session_id)
        
        # Apply approved applicability changes
        if gid in approved_changes:
            for ctx, changes in approved_changes[gid].items():
                for change in changes:
                    field = change["field"]
                    entry[ctx][field] = change["proposed_value"]
                    print(f"  {gid} ({ctx}): Applied {field} = {change['proposed_value']}", file=sys.stderr)
        
        # Update in mappings
        mappings["mappings"][idx] = entry
        updated_count += 1
    
    # Report ADD-6 mismatches as warnings
    if add6_mismatches:
        print(f"\nWARNING: ADD-6 data changed for {len(add6_mismatches)} guideline(s):", file=sys.stderr)
        for gid, diffs in add6_mismatches[:5]:
            print(f"  {gid}:", file=sys.stderr)
            for diff in diffs[:3]:
                print(f"    {diff}", file=sys.stderr)
        if len(add6_mismatches) > 5:
            print(f"  ... and {len(add6_mismatches) - 5} more", file=sys.stderr)
    
    return mappings, updated_count, upgrade_stats


def update_progress_v2(
    progress: dict,
    report: dict,
    session_id: int,
) -> tuple[dict, int, int]:
    """
    Update verification progress with v2 per-context status.
    
    Returns:
        (updated_progress, all_rust_verified, safe_rust_verified)
    """
    batch_id = report["batch_id"]
    progress_version = progress.get("schema_version", "1.0")
    
    # Find the batch
    target_batch = None
    for batch in progress["batches"]:
        if batch["batch_id"] == batch_id:
            target_batch = batch
            break
    
    if not target_batch:
        print(f"ERROR: Batch {batch_id} not found in progress file", file=sys.stderr)
        return progress, 0, 0
    
    # Build guideline lookup
    guideline_lookup = {g["guideline_id"]: g for g in target_batch["guidelines"]}
    
    all_rust_count = 0
    safe_rust_count = 0
    
    for g in report["guidelines"]:
        gid = g["guideline_id"]
        vd = g.get("verification_decision")
        
        if vd is None:
            continue
        
        if gid not in guideline_lookup:
            print(f"WARNING: {gid} not found in batch {batch_id}, skipping", file=sys.stderr)
            continue
        
        pg = guideline_lookup[gid]
        
        # Ensure v2 structure in progress
        if "all_rust" not in pg:
            pg["all_rust"] = {"verified": False}
        if "safe_rust" not in pg:
            pg["safe_rust"] = {"verified": False}
        
        # Update per-context verification status
        for context in ["all_rust", "safe_rust"]:
            ctx_decision = vd.get(context, {})
            if ctx_decision.get("decision") is not None:
                pg[context]["verified"] = True
                pg[context]["verified_by_session"] = session_id
                
                if context == "all_rust":
                    all_rust_count += 1
                else:
                    safe_rust_count += 1
        
        # Update legacy status field for compatibility
        if pg["all_rust"]["verified"] and pg["safe_rust"]["verified"]:
            pg["status"] = "verified"
            pg["verified"] = True
        elif pg["all_rust"]["verified"] or pg["safe_rust"]["verified"]:
            pg["status"] = "partial"
            pg["verified"] = False
    
    # Update batch status
    all_both_verified = all(
        g.get("all_rust", {}).get("verified") and g.get("safe_rust", {}).get("verified")
        for g in target_batch["guidelines"]
    )
    if all_both_verified:
        target_batch["status"] = "completed"
        print(f"Batch {batch_id} marked as completed", file=sys.stderr)
    else:
        target_batch["status"] = "in_progress"
    
    # Update progress schema version if it was v1
    if progress_version == "1.0":
        progress["schema_version"] = "2.0"
    
    # Update or add session
    session_exists = any(s["session_id"] == session_id for s in progress.get("sessions", []))
    if not session_exists:
        if "sessions" not in progress:
            progress["sessions"] = []
        progress["sessions"].append({
            "session_id": session_id,
            "date": date.today().isoformat(),
            "batch_id": batch_id,
            "all_rust_verified": all_rust_count,
            "safe_rust_verified": safe_rust_count,
        })
    else:
        for s in progress["sessions"]:
            if s["session_id"] == session_id:
                s["all_rust_verified"] = s.get("all_rust_verified", 0) + all_rust_count
                s["safe_rust_verified"] = s.get("safe_rust_verified", 0) + safe_rust_count
                s["date"] = date.today().isoformat()
    
    return progress, all_rust_count, safe_rust_count


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
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: Apply verified changes (upgrades all entries to v3.0)"
    )
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
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
        report_path = get_batch_report_path(root, args.standard, args.batch, args.session)
    elif args.batch_report is not None:
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
    
    report_version = report.get("schema_version", "1.0")
    print(f"Batch report schema: {report_version}", file=sys.stderr)
    
    # Validate batch report
    errors = validate_batch_report(report)
    if errors:
        print("ERROR: Batch report validation failed:", file=sys.stderr)
        for e in errors[:10]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors", file=sys.stderr)
        sys.exit(1)
    
    # Check applicability changes
    changes = report.get("applicability_changes", [])
    pending = [c for c in changes if c.get("approved") is None]
    approved = [c for c in changes if c.get("approved") is True]
    
    if pending:
        print(f"WARNING: {len(pending)} unapproved applicability changes", file=sys.stderr)
        if args.apply_applicability_changes:
            print("  Only approved changes will be applied.", file=sys.stderr)
    
    # Load ADD-6 data
    add6_all = load_add6_data(root)
    if not add6_all:
        print("WARNING: No ADD-6 data available. Entries will not have misra_add6 blocks.", file=sys.stderr)
    
    # Load current files
    mappings_path = get_standard_mappings_path(root, args.standard)
    progress_path = get_verification_progress_path(root, args.standard)
    
    mappings = load_json(mappings_path, "Mappings")
    progress = load_json(progress_path, "Verification progress")
    
    # Apply updates (always output v3.0)
    print(f"\nApplying changes from batch {report['batch_id']}...", file=sys.stderr)
    
    updated_mappings, mapping_count, upgrade_stats = update_mappings_to_v3(
        mappings, report, args.session, args.apply_applicability_changes, add6_all
    )
    updated_progress, all_rust_count, safe_rust_count = update_progress_v2(
        progress, report, args.session
    )
    
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Guidelines updated: {mapping_count}", file=sys.stderr)
    print(f"  Upgrades:", file=sys.stderr)
    for upgrade_type, count in upgrade_stats.items():
        if count > 0:
            print(f"    {upgrade_type}: {count}", file=sys.stderr)
    print(f"  all_rust contexts verified: {all_rust_count}", file=sys.stderr)
    print(f"  safe_rust contexts verified: {safe_rust_count}", file=sys.stderr)
    
    if approved:
        print(f"  Applicability changes applied: {len(approved)}", file=sys.stderr)
    
    if args.dry_run:
        print("\n[DRY RUN] No files were modified.", file=sys.stderr)
        return
    
    # Save updated files
    save_json(mappings_path, updated_mappings, "Mappings")
    save_json(progress_path, updated_progress, "Verification progress")
    
    # Run validation
    if not args.skip_validation:
        if not run_validation(root):
            print("\nWARNING: Validation failed. Review changes manually.", file=sys.stderr)
            sys.exit(1)
    
    print("\nDone.", file=sys.stderr)


if __name__ == "__main__":
    main()
