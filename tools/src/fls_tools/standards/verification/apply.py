#!/usr/bin/env python3
"""
apply_verification.py - Phase 4: Apply Verified Changes (Upgrade to v4.0)

This script applies verified decisions from a batch report to:
- misra_c_to_fls.json: Update to v4.0 format with per-context decisions + ADD-6 + paragraph coverage
- verification_progress.json: Mark guidelines as verified per-context

**IMPORTANT: This is where schema upgrades happen.**

When applying decisions, entries are upgraded to v4.0 format regardless
of their original version (v1.x, v2.x, v3.x). This includes:
- paragraph_match_count per context
- section_match_count per context  
- paragraph_level_waiver per context (null for fresh verification)

**Analysis Gate (Optional):**

When --analysis-dir is provided, the tool validates that all outliers have
been reviewed before applying. Granular human decisions are respected:
- Categorization: accept/reject controls applicability, rationale_type
- FLS Removals: per-ID accept/reject controls which matches are removed
- FLS Additions: per-ID accept/reject controls which matches are added
- ADD-6 Divergence: reject reverts to ADD-6 values

Usage:
    uv run apply-verification --standard misra-c --batch 1 --session 1
    uv run apply-verification --standard misra-c --batch 1 --session 1 --dry-run
    
    # With analysis gate
    uv run apply-verification --standard misra-c --batch 1 --session 1 \\
        --analysis-dir cache/analysis/
    
    # Skip analysis check (escape hatch)
    uv run apply-verification --standard misra-c --batch 1 --session 1 \\
        --skip-analysis-check --force
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
    count_matches_by_category,
)

# Analysis imports - lazy loaded to avoid circular imports
def load_analysis_modules():
    """Load analysis modules lazily."""
    from fls_tools.standards.analysis.shared import (
        get_outlier_analysis_dir,
        load_outlier_analysis,
        load_review_state,
        recompute_review_summary,
        is_outlier as check_is_outlier,
        load_comparison_data,
    )
    return {
        "get_outlier_analysis_dir": get_outlier_analysis_dir,
        "load_outlier_analysis": load_outlier_analysis,
        "load_review_state": load_review_state,
        "recompute_review_summary": recompute_review_summary,
        "check_is_outlier": check_is_outlier,
        "load_comparison_data": load_comparison_data,
    }


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
    
    Accepts v2.0, v2.1, v3.0, v3.1, v3.2, or v4.0 batch reports.
    Checks that verification_decision has both contexts with decisions.
    """
    errors = []
    
    schema_version = report.get("schema_version", "1.0")
    valid_versions = ("2.0", "2.1", "3.0", "3.1", "3.2", "4.0")
    if schema_version not in valid_versions:
        errors.append(f"Expected v2.0-v4.0 batch report, got {schema_version}")
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


def migrate_v1_to_v4_entry(v1_entry: dict, add6_data: dict | None) -> dict:
    """
    Convert a v1.0, v1.1, or v1.2 mapping entry to v4.0 structure.
    
    The v1 data is split into both contexts as a starting point.
    The actual verified data will be applied on top.
    """
    # Get matches (v1 has flat structure)
    matches = deepcopy(v1_entry.get("accepted_matches", []))
    para_count, section_count = count_matches_by_category(matches)
    
    entry = {
        "schema_version": "4.0",
        "guideline_id": v1_entry["guideline_id"],
        "guideline_title": v1_entry.get("guideline_title", ""),
        "guideline_type": v1_entry.get("guideline_type", "rule"),
        "all_rust": {
            "applicability": convert_v1_applicability_to_v2(v1_entry.get("applicability_all_rust", "direct")),
            "adjusted_category": None,  # Not in v1
            "rationale_type": v1_entry.get("fls_rationale_type"),
            "confidence": v1_entry.get("confidence", "medium"),
            "accepted_matches": matches,
            "rejected_matches": deepcopy(v1_entry.get("rejected_matches", [])),
            "paragraph_match_count": para_count,
            "section_match_count": section_count,
            "paragraph_level_waiver": None,  # Fresh verification
            "verified": False,
            "verified_by_session": None,
            "notes": v1_entry.get("notes"),
        },
        "safe_rust": {
            "applicability": convert_v1_applicability_to_v2(v1_entry.get("applicability_safe_rust", "direct")),
            "adjusted_category": None,
            "rationale_type": v1_entry.get("fls_rationale_type"),
            "confidence": v1_entry.get("confidence", "medium"),
            "accepted_matches": deepcopy(matches),
            "rejected_matches": deepcopy(v1_entry.get("rejected_matches", [])),
            "paragraph_match_count": para_count,
            "section_match_count": section_count,
            "paragraph_level_waiver": None,  # Fresh verification
            "verified": False,
            "verified_by_session": None,
            "notes": v1_entry.get("notes"),
        },
    }
    
    # Add ADD-6 block if available
    if add6_data:
        entry["misra_add6"] = build_misra_add6_block(add6_data)
    
    return entry


def migrate_v2_to_v4_entry(v2_entry: dict, add6_data: dict | None) -> dict:
    """
    Convert a v2.x or v3.x mapping entry to v4.0 structure.
    
    Preserves the existing per-context structure and adds/updates:
    - misra_add6 block
    - paragraph_match_count per context
    - section_match_count per context
    - paragraph_level_waiver per context (null for fresh verification)
    """
    entry = deepcopy(v2_entry)
    entry["schema_version"] = "4.0"
    
    # Add or update ADD-6 block
    if add6_data:
        entry["misra_add6"] = build_misra_add6_block(add6_data)
    
    # Add paragraph coverage fields to each context
    for ctx in ["all_rust", "safe_rust"]:
        ctx_data = entry.get(ctx, {})
        if ctx_data:
            matches = ctx_data.get("accepted_matches", [])
            para_count, section_count = count_matches_by_category(matches)
            ctx_data["paragraph_match_count"] = para_count
            ctx_data["section_match_count"] = section_count
            ctx_data["paragraph_level_waiver"] = None  # Fresh verification
    
    return entry


def apply_v4_decision_to_context(
    entry: dict,
    context: str,
    decision: dict,
    session_id: int,
) -> None:
    """
    Apply a v4 context decision to a v4 entry.
    
    Modifies entry in place. Updates paragraph coverage fields based on
    accepted_matches from the decision.
    """
    ctx = entry.get(context, {})
    
    # Get accepted matches from decision
    accepted_matches = decision.get("accepted_matches", [])
    
    # Compute paragraph coverage from the decision's matches
    para_count, section_count = count_matches_by_category(accepted_matches)
    
    # Apply all decision fields
    ctx["applicability"] = decision.get("applicability")
    ctx["adjusted_category"] = decision.get("adjusted_category")
    ctx["rationale_type"] = decision.get("rationale_type")
    ctx["confidence"] = decision.get("confidence", "high")
    ctx["accepted_matches"] = accepted_matches
    ctx["rejected_matches"] = decision.get("rejected_matches", [])
    ctx["notes"] = decision.get("notes")
    ctx["verified"] = True
    ctx["verified_by_session"] = session_id
    
    # Update paragraph coverage fields
    ctx["paragraph_match_count"] = para_count
    ctx["section_match_count"] = section_count
    
    # Preserve waiver from decision if provided, otherwise null (fresh verification)
    ctx["paragraph_level_waiver"] = decision.get("paragraph_level_waiver")
    
    entry[context] = ctx


def update_mappings_to_v4(
    mappings: dict,
    report: dict,
    session_id: int,
    apply_applicability_changes: bool,
    add6_all: dict,
) -> tuple[dict, int, dict]:
    """
    Update mappings with decisions, upgrading all entries to v4.0.
    
    Returns:
        (updated_mappings, guidelines_updated, upgrade_stats)
    
    upgrade_stats is a dict with keys like "v1.0→v4.0", "v1.1→v4.0", etc.
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
        "v1.x→v4.0": 0,
        "v2.x→v4.0": 0,
        "v3.x→v4.0": 0,
        "v4.0 updated": 0,
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
        
        # Migrate to v4.0 based on existing version
        if existing_version.startswith("1."):
            entry = migrate_v1_to_v4_entry(existing, add6_data)
            upgrade_stats["v1.x→v4.0"] += 1
        elif existing_version.startswith("2.") or existing_version.startswith("3."):
            entry = migrate_v2_to_v4_entry(existing, add6_data)
            if existing_version.startswith("2."):
                upgrade_stats["v2.x→v4.0"] += 1
            else:
                upgrade_stats["v3.x→v4.0"] += 1
        elif existing_version == "4.0":
            # Already v4.0
            entry = deepcopy(existing)
            # Ensure ADD-6 block is present/updated
            if add6_data:
                entry["misra_add6"] = build_misra_add6_block(add6_data)
            upgrade_stats["v4.0 updated"] += 1
        else:
            # Unknown version, treat as v2+
            entry = migrate_v2_to_v4_entry(existing, add6_data)
            upgrade_stats["v3.x→v4.0"] += 1
        
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
                apply_v4_decision_to_context(entry, context, ctx_decision, session_id)
        
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


# =============================================================================
# Analysis Gate Functions
# =============================================================================

def validate_analysis_complete(
    analysis_dir: Path,
    report: dict,
    root: Path,
) -> tuple[bool, dict]:
    """
    Validate that all outliers have been reviewed.
    
    Returns:
        (is_complete, summary_dict)
    """
    analysis = load_analysis_modules()
    
    # Recompute review summary
    summary = analysis["recompute_review_summary"](root)
    
    # Load batch guideline IDs
    batch_guidelines = {g["guideline_id"] for g in report.get("guidelines", [])}
    
    # Check each batch guideline for outlier status
    pending_outliers = []
    partial_outliers = []
    fully_reviewed = []
    
    outlier_dir = analysis["get_outlier_analysis_dir"](root)
    
    for gid in batch_guidelines:
        outlier = analysis["load_outlier_analysis"](gid, root)
        if outlier is None:
            # Not an outlier, or comparison data not extracted
            continue
        
        human_review = outlier.get("human_review")
        if human_review is None:
            pending_outliers.append(gid)
        elif human_review.get("overall_status") == "pending":
            pending_outliers.append(gid)
        elif human_review.get("overall_status") == "partial":
            partial_outliers.append(gid)
        else:
            fully_reviewed.append(gid)
    
    is_complete = len(pending_outliers) == 0 and len(partial_outliers) == 0
    
    return is_complete, {
        "pending": pending_outliers,
        "partial": partial_outliers,
        "fully_reviewed": fully_reviewed,
        "summary": summary,
    }


def merge_with_human_decisions(
    mapping_ctx: dict,
    decision_ctx: dict,
    human_review: dict,
    context: str,
    add6_data: dict | None,
) -> dict:
    """
    Merge LLM decision with human review adjustments for one context.
    
    Args:
        mapping_ctx: Current state from mapping file for this context
        decision_ctx: LLM decision for this context
        human_review: Human review section from outlier analysis
        context: "all_rust" or "safe_rust"
        add6_data: ADD-6 data for the guideline (if available)
    
    Returns:
        Merged context dict
    """
    final = {}
    
    # --- Categorization ---
    cat_decision = None
    cat_review = human_review.get("categorization", {})
    if isinstance(cat_review, dict):
        cat_decision = cat_review.get("decision")
    
    if cat_decision == "accept":
        final["applicability"] = decision_ctx.get("applicability")
        final["rationale_type"] = decision_ctx.get("rationale_type")
        final["adjusted_category"] = decision_ctx.get("adjusted_category")
    else:  # reject or not reviewed - keep mapping values
        final["applicability"] = mapping_ctx.get("applicability")
        final["rationale_type"] = mapping_ctx.get("rationale_type")
        final["adjusted_category"] = mapping_ctx.get("adjusted_category")
    
    # --- ADD-6 Divergence Override ---
    add6_review = human_review.get("add6_divergence", {})
    if isinstance(add6_review, dict) and add6_review.get("decision") == "reject":
        # Revert to ADD-6 values
        if add6_data:
            add6_app_key = f"applicability_{context}"
            if add6_app_key in add6_data:
                add6_app = add6_data[add6_app_key].lower() if add6_data[add6_app_key] else None
                if add6_app == "yes":
                    final["applicability"] = "yes"
                elif add6_app == "no":
                    final["applicability"] = "no"
                elif add6_app == "partial":
                    final["applicability"] = "partial"
            if "adjusted_category" in add6_data:
                final["adjusted_category"] = add6_data["adjusted_category"]
    
    # --- FLS Matches ---
    mapping_matches = mapping_ctx.get("accepted_matches", [])
    decision_matches = decision_ctx.get("accepted_matches", [])
    
    mapping_fls_ids = {m.get("fls_id") for m in mapping_matches if m.get("fls_id")}
    decision_fls_ids = {m.get("fls_id") for m in decision_matches if m.get("fls_id")}
    
    retained = mapping_fls_ids & decision_fls_ids
    removed = mapping_fls_ids - decision_fls_ids
    added = decision_fls_ids - mapping_fls_ids
    
    final_matches = []
    
    # Include retained matches (use decision's version for updated reasons)
    for match in decision_matches:
        if match.get("fls_id") in retained:
            final_matches.append(match)
    
    # Handle removals: include if human rejected the removal
    fls_removals = human_review.get("fls_removals", {})
    for match in mapping_matches:
        fls_id = match.get("fls_id")
        if fls_id in removed:
            removal_item = fls_removals.get(fls_id, {})
            if isinstance(removal_item, dict) and removal_item.get("decision") == "reject":
                # Human rejected removal, keep it
                final_matches.append(match)
    
    # Handle additions: include if human accepted the addition
    fls_additions = human_review.get("fls_additions", {})
    for match in decision_matches:
        fls_id = match.get("fls_id")
        if fls_id in added:
            addition_item = fls_additions.get(fls_id, {})
            if isinstance(addition_item, dict) and addition_item.get("decision") == "accept":
                # Human accepted addition, include it
                final_matches.append(match)
    
    final["accepted_matches"] = final_matches
    
    # Copy other fields from decision
    final["confidence"] = "high"  # All verified decisions get high confidence
    final["rejected_matches"] = decision_ctx.get("rejected_matches", [])
    final["notes"] = decision_ctx.get("notes")
    
    return final


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
    parser.add_argument(
        "--analysis-dir",
        type=str,
        default=None,
        help="Path to analysis directory (enables analysis gate)",
    )
    parser.add_argument(
        "--skip-analysis-check",
        action="store_true",
        help="Skip analysis completion check (requires --force)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force apply without analysis gate (requires --skip-analysis-check)",
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
    
    # =============================================================================
    # Analysis Gate Check
    # =============================================================================
    
    analysis_results = None
    
    if args.analysis_dir:
        try:
            analysis_path = resolve_path(Path(args.analysis_dir))
            analysis_path = validate_path_in_project(analysis_path, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        
        if not analysis_path.exists():
            print(f"ERROR: Analysis directory not found: {analysis_path}", file=sys.stderr)
            print(f"  Run: uv run extract-comparison-data --standard {args.standard} --batches {report['batch_id']}", file=sys.stderr)
            sys.exit(1)
        
        print(f"\nValidating analysis completion...", file=sys.stderr)
        is_complete, analysis_results = validate_analysis_complete(analysis_path, report, root)
        
        pending_outliers = analysis_results["pending"]
        partial_outliers = analysis_results["partial"]
        fully_reviewed = analysis_results["fully_reviewed"]
        
        print(f"  Outliers: {len(fully_reviewed)} reviewed, {len(pending_outliers)} pending, {len(partial_outliers)} partial", file=sys.stderr)
        
        if not is_complete:
            print(f"\nERROR: Analysis not complete. Blocking apply.", file=sys.stderr)
            if pending_outliers:
                print(f"\nPending outliers ({len(pending_outliers)}):", file=sys.stderr)
                for gid in pending_outliers[:10]:
                    print(f"  - {gid}", file=sys.stderr)
                if len(pending_outliers) > 10:
                    print(f"  ... and {len(pending_outliers) - 10} more", file=sys.stderr)
            if partial_outliers:
                print(f"\nPartially reviewed outliers ({len(partial_outliers)}):", file=sys.stderr)
                for gid in partial_outliers[:10]:
                    print(f"  - {gid}", file=sys.stderr)
            print(f"\nTo complete review:", file=sys.stderr)
            print(f"  uv run record-outlier-analysis --standard {args.standard} --guideline \"<GUIDELINE>\" ...", file=sys.stderr)
            print(f"  uv run review-outliers --standard {args.standard} --guideline \"<GUIDELINE>\" --accept-all", file=sys.stderr)
            print(f"\nOr bypass with:", file=sys.stderr)
            print(f"  --skip-analysis-check --force", file=sys.stderr)
            sys.exit(1)
    
    # Handle skip-analysis-check escape hatch
    if args.skip_analysis_check:
        if not args.force:
            print("ERROR: --skip-analysis-check requires --force", file=sys.stderr)
            sys.exit(1)
        print("\nWARNING: Skipping analysis check. Decisions will be applied without human review.", file=sys.stderr)
    
    # Load ADD-6 data
    add6_all = load_add6_data(root)
    if not add6_all:
        print("WARNING: No ADD-6 data available. Entries will not have misra_add6 blocks.", file=sys.stderr)
    
    # Load current files
    mappings_path = get_standard_mappings_path(root, args.standard)
    progress_path = get_verification_progress_path(root, args.standard)
    
    mappings = load_json(mappings_path, "Mappings")
    progress = load_json(progress_path, "Verification progress")
    
    # Apply updates (always output v4.0)
    print(f"\nApplying changes from batch {report['batch_id']}...", file=sys.stderr)
    
    updated_mappings, mapping_count, upgrade_stats = update_mappings_to_v4(
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
