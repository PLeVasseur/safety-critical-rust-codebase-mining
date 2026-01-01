#!/usr/bin/env python3
"""
check_progress.py - Check Verification Progress (v2 Schema)

This script shows current verification status with per-context tracking:
- Overall progress: all_rust and safe_rust separately
- Current batch and its status
- Batch report and decisions directory status
- Worker assignment suggestions for remaining guidelines

Usage:
    uv run check-progress --standard misra-c
    uv run check-progress --standard misra-c --workers 4
"""

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_verification_cache_dir,
    get_verification_progress_path,
    get_standard_mappings_path,
    get_coding_standards_dir,
    VALID_STANDARDS,
    get_guideline_schema_version,
    is_v1,
    is_v2,
)


def load_json(path: Path) -> dict | None:
    """Load a JSON file, return None if not found."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def is_context_verified_in_decision(decision: dict, context: str) -> bool:
    """Check if a context has a completed decision in a decision file."""
    if not decision:
        return False
    
    version = decision.get("schema_version", "1.0")
    
    if version == "2.0":
        ctx_data = decision.get(context, {})
        return ctx_data.get("decision") is not None
    else:
        # v1: both contexts share the same decision
        return decision.get("decision") is not None


def is_context_verified_in_mapping(entry: dict, context: str) -> bool:
    """Check if a context is verified in a mapping file entry."""
    version = get_guideline_schema_version(entry)
    
    if version == "2.0":
        ctx_data = entry.get(context, {})
        return ctx_data.get("verified", False)
    else:
        # v1: check confidence (high = verified)
        return entry.get("confidence") == "high"


def find_batch_reports(cache_dir: Path) -> list[dict]:
    """Find all batch reports in cache/verification/{standard}/."""
    reports = []
    if not cache_dir.exists():
        return reports
    
    for f in cache_dir.glob("batch*_session*.json"):
        try:
            data = load_json(f)
            if data and "batch_id" in data and "session_id" in data:
                version = data.get("schema_version", "1.0")
                total = len(data.get("guidelines", []))
                
                if version == "2.0":
                    # Count per-context verification
                    all_rust_verified = 0
                    safe_rust_verified = 0
                    for g in data.get("guidelines", []):
                        vd = g.get("verification_decision", {})
                        if vd:
                            ar = vd.get("all_rust", {})
                            sr = vd.get("safe_rust", {})
                            if ar.get("decision"):
                                all_rust_verified += 1
                            if sr.get("decision"):
                                safe_rust_verified += 1
                    
                    reports.append({
                        "path": f,
                        "batch_id": data["batch_id"],
                        "session_id": data["session_id"],
                        "schema_version": version,
                        "total": total,
                        "all_rust_verified": all_rust_verified,
                        "safe_rust_verified": safe_rust_verified,
                        "both_verified": min(all_rust_verified, safe_rust_verified),
                        "generated_date": data.get("generated_date"),
                    })
                else:
                    # v1 report
                    verified = sum(
                        1 for g in data.get("guidelines", [])
                        if g.get("verification_decision", {}).get("decision")
                    )
                    reports.append({
                        "path": f,
                        "batch_id": data["batch_id"],
                        "session_id": data["session_id"],
                        "schema_version": version,
                        "total": total,
                        "verified": verified,
                        "generated_date": data.get("generated_date"),
                    })
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(reports, key=lambda r: (r["batch_id"], r["session_id"]))


def load_decision_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def validate_decision_file(path: Path, schema: dict | None) -> tuple[bool, str | None, dict | None]:
    """
    Validate a decision file.
    
    Returns:
        (is_valid, guideline_id, data)
    """
    data = load_json(path)
    if data is None:
        return False, None, None
    
    guideline_id = data.get("guideline_id")
    
    # Check filename matches guideline_id
    expected_filename = (guideline_id or "").replace(" ", "_") + ".json"
    if path.name != expected_filename:
        return False, guideline_id, None
    
    # Schema validation (warning only, don't fail)
    if schema:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError:
            # Still return the data for analysis even if schema fails
            pass
    
    return True, guideline_id, data


def find_decisions_directory(cache_dir: Path, batch_id: int) -> Path | None:
    """Find decisions directory for a batch."""
    decisions_dir = cache_dir / f"batch{batch_id}_decisions"
    if decisions_dir.exists() and decisions_dir.is_dir():
        return decisions_dir
    return None


def analyze_decisions_directory_v2(
    decisions_dir: Path,
    batch_guidelines: list[str],
    schema: dict | None,
) -> dict:
    """
    Analyze a decisions directory with v2 per-context tracking.
    
    Returns dict with per-context progress.
    """
    decision_files = list(decisions_dir.glob("*.json"))
    
    valid_count = 0
    invalid_count = 0
    invalid_files = []
    
    # Per-context tracking
    all_rust_decided = set()
    safe_rust_decided = set()
    both_decided = set()
    
    for path in decision_files:
        is_valid, guideline_id, data = validate_decision_file(path, schema)
        if is_valid and guideline_id and data:
            valid_count += 1
            
            version = data.get("schema_version", "1.0")
            if version == "2.0":
                ar = data.get("all_rust", {})
                sr = data.get("safe_rust", {})
                
                if ar.get("decision"):
                    all_rust_decided.add(guideline_id)
                if sr.get("decision"):
                    safe_rust_decided.add(guideline_id)
                if ar.get("decision") and sr.get("decision"):
                    both_decided.add(guideline_id)
            else:
                # v1: counts as both
                if data.get("decision"):
                    all_rust_decided.add(guideline_id)
                    safe_rust_decided.add(guideline_id)
                    both_decided.add(guideline_id)
        else:
            invalid_count += 1
            invalid_files.append(path.name)
    
    # Remaining by context
    all_rust_remaining = [g for g in batch_guidelines if g not in all_rust_decided]
    safe_rust_remaining = [g for g in batch_guidelines if g not in safe_rust_decided]
    both_remaining = [g for g in batch_guidelines if g not in both_decided]
    
    return {
        "total_files": len(decision_files),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "invalid_files": invalid_files,
        "all_rust_decided": all_rust_decided,
        "safe_rust_decided": safe_rust_decided,
        "both_decided": both_decided,
        "all_rust_remaining": all_rust_remaining,
        "safe_rust_remaining": safe_rust_remaining,
        "both_remaining": both_remaining,
    }


def suggest_worker_assignment(
    remaining_guidelines: list[str],
    num_workers: int,
) -> list[tuple[int, list[str]]]:
    """
    Suggest worker assignment for remaining guidelines.
    
    Returns list of (worker_num, guideline_list) tuples.
    """
    if not remaining_guidelines:
        return []
    
    assignments = []
    per_worker = len(remaining_guidelines) // num_workers
    remainder = len(remaining_guidelines) % num_workers
    
    start = 0
    for i in range(num_workers):
        count = per_worker + (1 if i < remainder else 0)
        if count > 0:
            worker_guidelines = remaining_guidelines[start:start + count]
            assignments.append((i + 1, worker_guidelines))
            start += count
    
    return assignments


def get_progress_from_mapping(root: Path, standard: str) -> dict:
    """
    Get verification progress from the mapping file.
    
    Detects v1/v2 per-entry and counts per-context verification.
    """
    mapping_path = get_standard_mappings_path(root, standard)
    data = load_json(mapping_path)
    
    if not data:
        return {"error": f"Mapping file not found: {mapping_path}"}
    
    total = 0
    all_rust_verified = 0
    safe_rust_verified = 0
    both_verified = 0
    v1_count = 0
    v2_count = 0
    
    for entry in data.get("mappings", []):
        total += 1
        version = get_guideline_schema_version(entry)
        
        if version == "2.0":
            v2_count += 1
            ar_verified = entry.get("all_rust", {}).get("verified", False)
            sr_verified = entry.get("safe_rust", {}).get("verified", False)
            
            if ar_verified:
                all_rust_verified += 1
            if sr_verified:
                safe_rust_verified += 1
            if ar_verified and sr_verified:
                both_verified += 1
        else:
            v1_count += 1
            # v1: confidence=high means verified (both contexts)
            if entry.get("confidence") == "high":
                all_rust_verified += 1
                safe_rust_verified += 1
                both_verified += 1
    
    return {
        "total": total,
        "all_rust_verified": all_rust_verified,
        "safe_rust_verified": safe_rust_verified,
        "both_verified": both_verified,
        "v1_count": v1_count,
        "v2_count": v2_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check verification progress with per-context tracking (v2)"
    )
    parser.add_argument(
        "--standard", "-s",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to check (e.g., misra-c, misra-cpp)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of workers for parallel assignment suggestions (default: 3)",
    )
    args = parser.parse_args()
    
    root = get_project_root()
    standard = args.standard
    
    # Load verification progress
    progress_path = get_verification_progress_path(root, standard)
    progress = load_json(progress_path)
    
    if not progress:
        print(f"ERROR: progress.json not found for {standard}", file=sys.stderr)
        print(f"       Expected at: {progress_path}", file=sys.stderr)
        print(f"       Run: uv run scaffold-progress --standard {standard}", file=sys.stderr)
        sys.exit(1)
    
    progress_version = progress.get("schema_version", "1.0")
    
    # Get progress from mapping file
    mapping_progress = get_progress_from_mapping(root, standard)
    
    # Find sessions info
    sessions = progress.get("sessions", [])
    last_session = max((s["session_id"] for s in sessions), default=0)
    next_session = last_session + 1
    
    # Find current batch (first non-completed)
    current_batch = None
    for batch in progress.get("batches", []):
        if batch["status"] != "completed":
            current_batch = batch
            break
    
    # Find batch reports
    cache_dir = get_verification_cache_dir(root, standard)
    batch_reports = find_batch_reports(cache_dir)
    
    # Output header
    print("=" * 60)
    print(f"VERIFICATION PROGRESS: {standard}")
    print("=" * 60)
    print()
    print(f"Progress schema version: {progress_version}")
    print(f"Last session: {last_session}")
    print(f"Next session: {next_session}")
    print()
    
    # Mapping file progress
    print("-" * 60)
    print("MAPPING FILE PROGRESS")
    print("-" * 60)
    if "error" in mapping_progress:
        print(f"  {mapping_progress['error']}")
    else:
        total = mapping_progress["total"]
        ar = mapping_progress["all_rust_verified"]
        sr = mapping_progress["safe_rust_verified"]
        both = mapping_progress["both_verified"]
        v1 = mapping_progress["v1_count"]
        v2 = mapping_progress["v2_count"]
        
        print(f"Total guidelines: {total}")
        print(f"  all_rust verified:  {ar}/{total} ({100*ar/total:.0f}%)")
        print(f"  safe_rust verified: {sr}/{total} ({100*sr/total:.0f}%)")
        print(f"  Both verified:      {both}/{total} ({100*both/total:.0f}%)")
        print()
        print(f"Schema versions: {v1} v1 entries, {v2} v2 entries")
        if v1 > 0 and v2 == 0:
            print("  (All entries are v1 - will be migrated to v2 when apply-verification runs)")
    print()
    
    # Load decision schema
    decision_schema = load_decision_schema(root)
    
    # Current batch details
    if current_batch:
        batch_id = current_batch["batch_id"]
        batch_guidelines = [g["guideline_id"] for g in current_batch.get("guidelines", [])]
        
        print("-" * 60)
        print(f"CURRENT BATCH: {batch_id} ({current_batch['name']})")
        print("-" * 60)
        print(f"Status: {current_batch['status']}")
        print(f"Guidelines in batch: {len(batch_guidelines)}")
        print()
        
        # Check for decisions directory
        decisions_dir = find_decisions_directory(cache_dir, batch_id)
        decisions_analysis = None
        
        if decisions_dir:
            decisions_analysis = analyze_decisions_directory_v2(
                decisions_dir, batch_guidelines, decision_schema
            )
            
            print("Decisions Directory:")
            print(f"  Path: {decisions_dir.relative_to(root)}")
            print(f"  Files: {decisions_analysis['valid_count']} valid, {decisions_analysis['invalid_count']} invalid")
            print()
            print("  Per-context progress:")
            ar_done = len(decisions_analysis["all_rust_decided"])
            sr_done = len(decisions_analysis["safe_rust_decided"])
            both_done = len(decisions_analysis["both_decided"])
            total = len(batch_guidelines)
            
            print(f"    all_rust:  {ar_done}/{total} ({100*ar_done/total:.0f}%)")
            print(f"    safe_rust: {sr_done}/{total} ({100*sr_done/total:.0f}%)")
            print(f"    Both:      {both_done}/{total} ({100*both_done/total:.0f}%)")
            
            if decisions_analysis["invalid_files"]:
                print()
                print(f"  Invalid files: {', '.join(decisions_analysis['invalid_files'][:5])}")
            
            # Show guidelines status
            remaining_both = decisions_analysis["both_remaining"]
            if remaining_both:
                print()
                print(f"Guidelines needing verification ({len(remaining_both)}):")
                for gid in remaining_both[:10]:
                    ar_status = "✓" if gid in decisions_analysis["all_rust_decided"] else "○"
                    sr_status = "✓" if gid in decisions_analysis["safe_rust_decided"] else "○"
                    print(f"  {gid:<15} all_rust {ar_status}  safe_rust {sr_status}")
                if len(remaining_both) > 10:
                    print(f"  ... and {len(remaining_both) - 10} more")
                
                # Worker assignment
                print()
                print(f"Worker assignment ({args.workers} workers):")
                assignments = suggest_worker_assignment(remaining_both, args.workers)
                for worker_num, worker_guidelines in assignments:
                    if worker_guidelines:
                        print(f"  Worker {worker_num}: {worker_guidelines[0]} -> {worker_guidelines[-1]} ({len(worker_guidelines)} guidelines)")
            else:
                print()
                print("All guidelines in batch have both contexts verified!")
                print("Ready for merge and apply.")
        
        # Batch report
        matching_reports = [r for r in batch_reports if r["batch_id"] == batch_id]
        
        if matching_reports:
            latest = max(matching_reports, key=lambda r: r["session_id"])
            print()
            print("Batch Report:")
            print(f"  Path: {latest['path'].relative_to(root)}")
            print(f"  Session: {latest['session_id']}")
            print(f"  Schema: {latest.get('schema_version', '1.0')}")
            
            if latest.get("schema_version") == "2.0":
                ar = latest.get("all_rust_verified", 0)
                sr = latest.get("safe_rust_verified", 0)
                both = latest.get("both_verified", 0)
                total = latest["total"]
                print(f"  all_rust verified:  {ar}/{total}")
                print(f"  safe_rust verified: {sr}/{total}")
                print(f"  Both verified:      {both}/{total}")
            else:
                print(f"  Verified: {latest.get('verified', 0)}/{latest['total']}")
            
            if decisions_dir and decisions_analysis:
                both_done = len(decisions_analysis["both_decided"])
                if both_done > 0:
                    print()
                    print("To merge decisions:")
                    print(f"  uv run merge-decisions --standard {standard} --batch {batch_id} --session {latest['session_id']}")
        else:
            print()
            print("No batch report found.")
            print()
            print("To generate batch report:")
            print(f"  uv run verify-batch --standard {standard} --batch {batch_id} --session {next_session}")
    else:
        print("All batches completed!")
    
    # Show all batches summary
    print()
    print("-" * 60)
    print("ALL BATCHES")
    print("-" * 60)
    
    if progress_version == "2.0":
        print(f"{'Batch':<6} {'Name':<25} {'Status':<12} {'all_rust':<10} {'safe_rust':<10} {'Both':<10}")
        print("-" * 60)
        
        for batch in progress.get("batches", []):
            batch_guidelines = batch.get("guidelines", [])
            total = len(batch_guidelines)
            
            ar_verified = sum(
                1 for g in batch_guidelines
                if g.get("all_rust", {}).get("verified", False)
            )
            sr_verified = sum(
                1 for g in batch_guidelines
                if g.get("safe_rust", {}).get("verified", False)
            )
            both_verified = sum(
                1 for g in batch_guidelines
                if g.get("all_rust", {}).get("verified", False) and g.get("safe_rust", {}).get("verified", False)
            )
            
            print(f"{batch['batch_id']:<6} {batch['name'][:25]:<25} {batch['status']:<12} {ar_verified}/{total:<6} {sr_verified}/{total:<6} {both_verified}/{total:<6}")
    else:
        # v1 progress format
        print(f"{'Batch':<6} {'Name':<30} {'Status':<12} {'Verified':<10} {'Pending':<10}")
        print("-" * 60)
        
        for batch in progress.get("batches", []):
            verified = sum(1 for g in batch.get("guidelines", []) if g.get("verified", False))
            pending = sum(1 for g in batch.get("guidelines", []) if not g.get("verified", False))
            print(f"{batch['batch_id']:<6} {batch['name'][:30]:<30} {batch['status']:<12} {verified:<10} {pending:<10}")
    
    print()


if __name__ == "__main__":
    main()
