#!/usr/bin/env python3
"""
reset_batch.py - Reset verification decisions for a batch

This tool resets verification decisions to allow re-verification of guidelines.
It can reset an entire batch or specific guidelines within a batch.

Supports both v1.0 (flat) and v2.0 (per-context) progress formats.

What it resets:
- In batch report (cache/verification/batchN_sessionM.json):
  - Sets verification_decision to null for affected guidelines
  - Clears applicability_changes array
- In decision files (cache/verification/batchN_decisions/):
  - Deletes decision files for affected guidelines (with confirmation)
- In verification_progress.json:
  - v1: Sets status to "pending" for affected guidelines
  - v2: Sets verified=false for specified context(s)

Usage:
    # Reset all guidelines in batch 3 (both contexts in v2)
    uv run reset-batch --standard misra-c --batch 3

    # Reset only all_rust context for all guidelines in batch 3
    uv run reset-batch --standard misra-c --batch 3 --context all_rust

    # Reset specific guidelines in batch 3
    uv run reset-batch --standard misra-c --batch 3 --guidelines "Rule 22.1,Rule 22.2"

    # Preview changes without writing
    uv run reset-batch --standard misra-c --batch 3 --dry-run

    # Specify a specific batch report file
    uv run reset-batch --standard misra-c --batch 3 --batch-report ../cache/verification/batch3_session5.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from fls_tools.shared import (
    get_project_root,
    get_verification_progress_path,
    get_verification_cache_dir,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
    VALID_STANDARDS,
)
from fls_tools.shared.schema_version import (
    get_progress_schema_version,
    get_batch_report_schema_version,
)

Context = Literal["all_rust", "safe_rust", "both"]


def find_batch_report(root: Path, standard: str, batch_id: int) -> Path | None:
    """Find the most recent batch report for a given batch ID."""
    cache_dir = get_verification_cache_dir(root, standard)
    if not cache_dir.exists():
        return None
    
    # Find all batch reports for this batch, sorted by session (descending)
    reports = sorted(
        cache_dir.glob(f"batch{batch_id}_session*.json"),
        key=lambda p: int(p.stem.split("session")[1]),
        reverse=True
    )
    
    return reports[0] if reports else None


def find_decisions_dir(root: Path, standard: str, batch_id: int) -> Path | None:
    """Find the decisions directory for a batch."""
    cache_dir = get_verification_cache_dir(root, standard)
    decisions_dir = cache_dir / f"batch{batch_id}_decisions"
    return decisions_dir if decisions_dir.exists() else None


def reset_batch_report(
    report_path: Path,
    guideline_ids: list[str] | None,
    context: Context,
    dry_run: bool
) -> tuple[int, list[str]]:
    """
    Reset verification decisions in a batch report.
    
    For v2 batch reports with per-context decisions, respects the --context flag.
    
    Returns:
        Tuple of (count of reset guidelines, list of reset guideline IDs)
    """
    with open(report_path) as f:
        data = json.load(f)
    
    schema_version = get_batch_report_schema_version(data)
    reset_ids = []
    
    for guideline in data.get("guidelines", []):
        gid = guideline.get("guideline_id")
        
        # If specific guidelines requested, only reset those
        if guideline_ids and gid not in guideline_ids:
            continue
        
        if schema_version == "2.0":
            # v2: Handle per-context verification decisions
            vd = guideline.get("verification_decision", {})
            if vd is None:
                vd = {}
            
            reset_needed = False
            if context in ("all_rust", "both") and vd.get("all_rust", {}).get("decision") is not None:
                reset_needed = True
                if not dry_run:
                    if "all_rust" in vd:
                        vd["all_rust"]["decision"] = None
                        vd["all_rust"]["confidence"] = None
                        vd["all_rust"]["rationale_type"] = None
                        vd["all_rust"]["accepted_matches"] = []
                        vd["all_rust"]["rejected_matches"] = []
                        vd["all_rust"]["search_tools_used"] = []
            
            if context in ("safe_rust", "both") and vd.get("safe_rust", {}).get("decision") is not None:
                reset_needed = True
                if not dry_run:
                    if "safe_rust" in vd:
                        vd["safe_rust"]["decision"] = None
                        vd["safe_rust"]["confidence"] = None
                        vd["safe_rust"]["rationale_type"] = None
                        vd["safe_rust"]["accepted_matches"] = []
                        vd["safe_rust"]["rejected_matches"] = []
                        vd["safe_rust"]["search_tools_used"] = []
            
            if reset_needed:
                reset_ids.append(gid)
        else:
            # v1: Simple flat structure
            if guideline.get("verification_decision") is not None:
                reset_ids.append(gid)
                if not dry_run:
                    guideline["verification_decision"] = None
    
    # Clear applicability_changes array
    if not dry_run and data.get("applicability_changes"):
        data["applicability_changes"] = []
    
    if not dry_run and reset_ids:
        with open(report_path, "w") as f:
            json.dump(data, f, indent=2)
    
    return len(reset_ids), reset_ids


def reset_decision_files(
    decisions_dir: Path,
    guideline_ids: list[str] | None,
    context: Context,
    dry_run: bool,
    confirm: bool = True
) -> tuple[int, list[str]]:
    """
    Reset or delete decision files in a batch's decisions directory.
    
    For v2 decision files, if only one context is being reset, the file is
    modified to clear that context. If both contexts are reset, the file is deleted.
    
    Returns:
        Tuple of (count of affected files, list of affected guideline IDs)
    """
    affected_ids = []
    files_to_delete = []
    files_to_modify = []
    
    for decision_file in decisions_dir.glob("*.json"):
        with open(decision_file) as f:
            data = json.load(f)
        
        gid = data.get("guideline_id")
        if guideline_ids and gid not in guideline_ids:
            continue
        
        schema_version = data.get("schema_version", "1.0")
        
        if schema_version == "2.0":
            has_all_rust = data.get("all_rust", {}).get("decision") is not None
            has_safe_rust = data.get("safe_rust", {}).get("decision") is not None
            
            if context == "both":
                # Delete entire file if either context has data
                if has_all_rust or has_safe_rust:
                    files_to_delete.append((decision_file, gid))
                    affected_ids.append(gid)
            elif context == "all_rust":
                if has_all_rust:
                    if has_safe_rust:
                        # Modify file to clear only all_rust
                        files_to_modify.append((decision_file, gid, "all_rust"))
                    else:
                        # Delete file since only all_rust has data
                        files_to_delete.append((decision_file, gid))
                    affected_ids.append(gid)
            else:  # safe_rust
                if has_safe_rust:
                    if has_all_rust:
                        # Modify file to clear only safe_rust
                        files_to_modify.append((decision_file, gid, "safe_rust"))
                    else:
                        # Delete file since only safe_rust has data
                        files_to_delete.append((decision_file, gid))
                    affected_ids.append(gid)
        else:
            # v1: Always delete the file
            files_to_delete.append((decision_file, gid))
            affected_ids.append(gid)
    
    if not affected_ids:
        return 0, []
    
    if dry_run:
        if files_to_delete:
            print(f"  Would delete {len(files_to_delete)} decision file(s)")
        if files_to_modify:
            print(f"  Would modify {len(files_to_modify)} decision file(s)")
        return len(affected_ids), affected_ids
    
    if confirm and (files_to_delete or files_to_modify):
        print(f"\nWARNING: This will delete/modify {len(affected_ids)} decision file(s):")
        for f, gid in files_to_delete:
            print(f"  DELETE: {f.name} ({gid})")
        for f, gid, ctx in files_to_modify:
            print(f"  MODIFY: {f.name} ({gid}) - clear {ctx}")
        response = input("\nProceed? [y/N] ")
        if response.lower() != "y":
            print("Aborted")
            return 0, []
    
    # Delete files
    for decision_file, gid in files_to_delete:
        decision_file.unlink()
    
    # Modify files (clear specific context)
    for decision_file, gid, ctx in files_to_modify:
        with open(decision_file) as f:
            data = json.load(f)
        
        data[ctx] = {
            "decision": None,
            "applicability": None,
            "adjusted_category": None,
            "rationale_type": None,
            "confidence": None,
            "accepted_matches": [],
            "rejected_matches": [],
            "search_tools_used": [],
            "notes": None
        }
        
        with open(decision_file, "w") as f:
            json.dump(data, f, indent=2)
    
    return len(affected_ids), affected_ids


def reset_verification_progress_v1(
    data: dict,
    batch_id: int,
    guideline_ids: list[str] | None,
    dry_run: bool
) -> tuple[int, list[str]]:
    """
    Reset v1 format verification progress.
    
    Returns:
        Tuple of (count of reset guidelines, list of reset guideline IDs)
    """
    reset_ids = []
    
    # Find the batch
    for batch in data.get("batches", []):
        if batch.get("batch_id") != batch_id:
            continue
        
        for guideline in batch.get("guidelines", []):
            gid = guideline.get("guideline_id")
            
            # If specific guidelines requested, only reset those
            if guideline_ids and gid not in guideline_ids:
                continue
            
            # Reset if currently verified
            if guideline.get("status") == "verified":
                reset_ids.append(gid)
                if not dry_run:
                    guideline["status"] = "pending"
                    guideline["verified_date"] = None
                    guideline["session_id"] = None
        
        # Update batch status if we reset any guidelines
        if not dry_run and reset_ids:
            batch["status"] = "in_progress"
        
        break
    
    # Update summary counts
    if not dry_run and reset_ids:
        # Recompute summary
        total_verified = 0
        total_pending = 0
        by_batch = {}
        
        for batch in data.get("batches", []):
            bid = str(batch["batch_id"])
            verified = sum(1 for g in batch.get("guidelines", []) if g.get("status") == "verified")
            pending = sum(1 for g in batch.get("guidelines", []) if g.get("status") == "pending")
            total_verified += verified
            total_pending += pending
            by_batch[bid] = {"verified": verified, "pending": pending}
        
        data["summary"]["total_verified"] = total_verified
        data["summary"]["total_pending"] = total_pending
        data["summary"]["by_batch"] = by_batch
        data["summary"]["last_updated"] = datetime.now().isoformat()
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    
    return len(reset_ids), reset_ids


def reset_verification_progress_v2(
    data: dict,
    batch_id: int,
    guideline_ids: list[str] | None,
    context: Context,
    dry_run: bool
) -> tuple[int, list[str], dict[str, list[str]]]:
    """
    Reset v2 format verification progress with per-context tracking.
    
    Returns:
        Tuple of (count of reset guidelines, list of reset guideline IDs, 
                  dict mapping context -> list of reset IDs)
    """
    reset_ids = []
    reset_by_context: dict[str, list[str]] = {"all_rust": [], "safe_rust": []}
    
    # Find the batch
    for batch in data.get("batches", []):
        if batch.get("batch_id") != batch_id:
            continue
        
        for guideline in batch.get("guidelines", []):
            gid = guideline.get("guideline_id")
            
            # If specific guidelines requested, only reset those
            if guideline_ids and gid not in guideline_ids:
                continue
            
            reset_happened = False
            
            # Reset all_rust if requested
            if context in ("all_rust", "both"):
                all_rust = guideline.get("all_rust", {})
                if all_rust.get("verified"):
                    reset_by_context["all_rust"].append(gid)
                    reset_happened = True
                    if not dry_run:
                        all_rust["verified"] = False
                        all_rust["verified_date"] = None
                        all_rust["verified_by_session"] = None
            
            # Reset safe_rust if requested
            if context in ("safe_rust", "both"):
                safe_rust = guideline.get("safe_rust", {})
                if safe_rust.get("verified"):
                    reset_by_context["safe_rust"].append(gid)
                    reset_happened = True
                    if not dry_run:
                        safe_rust["verified"] = False
                        safe_rust["verified_date"] = None
                        safe_rust["verified_by_session"] = None
            
            if reset_happened and gid not in reset_ids:
                reset_ids.append(gid)
        
        # Update batch status if we reset any guidelines
        if not dry_run and reset_ids:
            batch["status"] = "in_progress"
        
        break
    
    # Update summary counts
    if not dry_run and reset_ids:
        all_rust_verified = 0
        safe_rust_verified = 0
        both_verified = 0
        pending = 0
        by_batch = {}
        
        for batch in data.get("batches", []):
            bid = str(batch["batch_id"])
            b_all_rust = 0
            b_safe_rust = 0
            b_both = 0
            b_pending = 0
            
            for g in batch.get("guidelines", []):
                ar_verified = g.get("all_rust", {}).get("verified", False)
                sr_verified = g.get("safe_rust", {}).get("verified", False)
                
                if ar_verified:
                    b_all_rust += 1
                    all_rust_verified += 1
                if sr_verified:
                    b_safe_rust += 1
                    safe_rust_verified += 1
                if ar_verified and sr_verified:
                    b_both += 1
                    both_verified += 1
                if not ar_verified and not sr_verified:
                    b_pending += 1
                    pending += 1
            
            by_batch[bid] = {
                "all_rust_verified": b_all_rust,
                "safe_rust_verified": b_safe_rust,
                "both_verified": b_both,
                "pending": b_pending
            }
        
        data["summary"]["all_rust_verified"] = all_rust_verified
        data["summary"]["safe_rust_verified"] = safe_rust_verified
        data["summary"]["both_verified"] = both_verified
        data["summary"]["pending"] = pending
        data["summary"]["by_batch"] = by_batch
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    
    return len(reset_ids), reset_ids, reset_by_context


def reset_verification_progress(
    root: Path,
    standard: str,
    batch_id: int,
    guideline_ids: list[str] | None,
    context: Context,
    dry_run: bool
) -> tuple[int, list[str], dict[str, list[str]] | None]:
    """
    Reset verification status in verification_progress.json.
    
    Detects schema version and delegates to appropriate handler.
    
    Returns:
        Tuple of (count of reset guidelines, list of reset guideline IDs,
                  optional dict of context -> reset IDs for v2)
    """
    progress_path = get_verification_progress_path(root, standard)
    
    if not progress_path.exists():
        print(f"WARNING: verification_progress.json not found at {progress_path}")
        return 0, [], None
    
    with open(progress_path) as f:
        data = json.load(f)
    
    schema_version = get_progress_schema_version(data)
    
    if schema_version == "2.0":
        count, ids, by_context = reset_verification_progress_v2(
            data, batch_id, guideline_ids, context, dry_run
        )
    else:
        count, ids = reset_verification_progress_v1(
            data, batch_id, guideline_ids, dry_run
        )
        by_context = None
    
    if not dry_run and ids:
        with open(progress_path, "w") as f:
            json.dump(data, f, indent=2)
    
    return count, ids, by_context


def main():
    parser = argparse.ArgumentParser(
        description="Reset verification decisions for a batch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Reset all guidelines in batch 3 (both contexts)
    uv run reset-batch --standard misra-c --batch 3

    # Reset only all_rust context in batch 3
    uv run reset-batch --standard misra-c --batch 3 --context all_rust

    # Reset specific guidelines
    uv run reset-batch --standard misra-c --batch 3 --guidelines "Rule 22.1,Rule 22.2"

    # Preview changes
    uv run reset-batch --standard misra-c --batch 3 --dry-run
        """
    )
    
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
    )
    
    parser.add_argument(
        "--batch", "-b",
        type=int,
        required=True,
        help="Batch ID to reset"
    )
    
    parser.add_argument(
        "--guidelines", "-g",
        type=str,
        default=None,
        help="Comma-separated list of guideline IDs to reset (default: all in batch)"
    )
    
    parser.add_argument(
        "--context", "-c",
        type=str,
        choices=["all_rust", "safe_rust", "both"],
        default="both",
        help="Context to reset (v2 only): all_rust, safe_rust, or both (default: both)"
    )
    
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to specific batch report file (default: auto-detect most recent)"
    )
    
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be reset without making changes"
    )
    
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt for decision file deletion"
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Parse guideline IDs if provided
    guideline_ids = None
    if args.guidelines:
        guideline_ids = [g.strip() for g in args.guidelines.split(",")]
    
    # Find or use specified batch report
    if args.batch_report:
        try:
            report_path = resolve_path(Path(args.batch_report))
            report_path = validate_path_in_project(report_path, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        report_path = find_batch_report(root, args.standard, args.batch)
    
    if args.dry_run:
        print("DRY RUN - No changes will be made\n")
    
    print(f"Schema context: {'v2 (per-context)' if args.context != 'both' else 'v1/v2 compatible'}")
    print(f"Context(s) to reset: {args.context}")
    print()
    
    # Reset batch report if it exists
    report_reset_count = 0
    report_reset_ids = []
    if report_path and report_path.exists():
        print(f"Batch report: {report_path}")
        report_reset_count, report_reset_ids = reset_batch_report(
            report_path, guideline_ids, args.context, args.dry_run
        )
        if report_reset_ids:
            print(f"  Would reset {report_reset_count} verification decisions:" if args.dry_run 
                  else f"  Reset {report_reset_count} verification decisions:")
            for gid in report_reset_ids:
                print(f"    - {gid}")
        else:
            print("  No verification decisions to reset")
    else:
        print(f"No batch report found for batch {args.batch}")
    
    print()
    
    # Reset decision files if directory exists
    decisions_dir = find_decisions_dir(root, args.standard, args.batch)
    decision_reset_count = 0
    decision_reset_ids = []
    if decisions_dir:
        print(f"Decisions directory: {decisions_dir}")
        decision_reset_count, decision_reset_ids = reset_decision_files(
            decisions_dir, guideline_ids, args.context, args.dry_run, confirm=not args.yes
        )
        if decision_reset_ids:
            print(f"  Affected {decision_reset_count} decision file(s):")
            for gid in decision_reset_ids:
                print(f"    - {gid}")
        else:
            print("  No decision files to reset")
    else:
        print(f"No decisions directory found for batch {args.batch}")
    
    print()
    
    # Reset verification progress
    print(f"Verification progress: {get_verification_progress_path(root, args.standard)}")
    progress_reset_count, progress_reset_ids, by_context = reset_verification_progress(
        root, args.standard, args.batch, guideline_ids, args.context, args.dry_run
    )
    
    if progress_reset_ids:
        if by_context:
            # v2 format - show per-context details
            print(f"  Would reset {progress_reset_count} guidelines:" if args.dry_run
                  else f"  Reset {progress_reset_count} guidelines:")
            if by_context.get("all_rust"):
                print(f"    all_rust ({len(by_context['all_rust'])}):")
                for gid in by_context["all_rust"][:5]:  # Show first 5
                    print(f"      - {gid}")
                if len(by_context["all_rust"]) > 5:
                    print(f"      ... and {len(by_context['all_rust']) - 5} more")
            if by_context.get("safe_rust"):
                print(f"    safe_rust ({len(by_context['safe_rust'])}):")
                for gid in by_context["safe_rust"][:5]:
                    print(f"      - {gid}")
                if len(by_context["safe_rust"]) > 5:
                    print(f"      ... and {len(by_context['safe_rust']) - 5} more")
        else:
            # v1 format
            print(f"  Would reset {progress_reset_count} guidelines to pending:" if args.dry_run
                  else f"  Reset {progress_reset_count} guidelines to pending:")
            for gid in progress_reset_ids:
                print(f"    - {gid}")
    else:
        print("  No guidelines to reset (none were verified)")
    
    print()
    
    # Summary
    total_reset = max(report_reset_count, progress_reset_count, decision_reset_count)
    if args.dry_run:
        print(f"Would reset {total_reset} guidelines in batch {args.batch}")
        print("\nRun without --dry-run to apply changes")
    else:
        print(f"Reset {total_reset} guidelines in batch {args.batch}")
        if report_path and report_path.exists():
            print(f"\nNext step: Re-run verification with:")
            print(f"  uv run verify-batch --standard {args.standard} --batch {args.batch} --session <NEW_SESSION_ID>")


if __name__ == "__main__":
    main()
