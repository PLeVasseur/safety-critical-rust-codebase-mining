#!/usr/bin/env python3
"""
merge_decisions.py - Merge decision files into a batch report.

This tool merges individual decision files from a decisions directory back into
a batch report for Phase 3 review. Supports v2.0 through v4.0 decision files.

Features:
- Merges v2.0/v2.1/v3.0/v3.1/v3.2/v4.0 decision files with all_rust and safe_rust contexts
- Populates verification_decision fields in batch report
- Aggregates proposed changes to top-level applicability_changes array
- Updates summary statistics with per-context counts
- Validates for duplicate search UUIDs across all decision files
- Preserves misra_add6_snapshot from v2.1+ decision files
- Warns if ADD-6 snapshot mismatches batch report's misra_add6
- Validates paragraph coverage fields (v3.2/v4.0) and warns on mismatches

Usage:
    # Using --batch for automatic path resolution (recommended):
    uv run merge-decisions --standard misra-c --batch 4 --session 6

    # With validation:
    uv run merge-decisions --standard misra-c --batch 4 --session 6 --validate

    # Dry run:
    uv run merge-decisions --standard misra-c --batch 4 --session 6 --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_coding_standards_dir,
    get_batch_decisions_dir,
    get_batch_report_path,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
    VALID_STANDARDS,
    check_add6_mismatch,
    count_matches_by_category,
)


def load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: dict) -> None:
    """Save a JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_decision_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def validate_decision(decision: dict, schema: dict) -> list[str]:
    """Validate a decision against the schema. Returns list of errors."""
    errors = []
    try:
        jsonschema.validate(instance=decision, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema error: {e.message}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema definition error: {e.message}")
    return errors


def find_guideline_index(report: dict, guideline_id: str) -> int | None:
    """Find guideline index in report by ID."""
    for i, g in enumerate(report.get("guidelines", [])):
        if g.get("guideline_id") == guideline_id:
            return i
    return None


def update_summary_v2(report: dict) -> None:
    """Update the batch report summary statistics for v2 format."""
    guidelines = report.get("guidelines", [])
    
    all_rust_verified = 0
    safe_rust_verified = 0
    both_verified = 0
    
    for g in guidelines:
        vd = g.get("verification_decision", {})
        if vd:
            ar = vd.get("all_rust", {})
            sr = vd.get("safe_rust", {})
            
            ar_done = ar.get("decision") is not None
            sr_done = sr.get("decision") is not None
            
            if ar_done:
                all_rust_verified += 1
            if sr_done:
                safe_rust_verified += 1
            if ar_done and sr_done:
                both_verified += 1
    
    changes = report.get("applicability_changes", [])
    changes_proposed = len(changes)
    changes_approved = sum(1 for c in changes if c.get("approved") is True)
    
    report["summary"] = {
        "total_guidelines": len(guidelines),
        "verified_count": both_verified,  # For backwards compatibility
        "all_rust_verified_count": all_rust_verified,
        "safe_rust_verified_count": safe_rust_verified,
        "applicability_changes_proposed": changes_proposed,
        "applicability_changes_approved": changes_approved,
    }


def load_decision_files(
    decisions_dir: Path,
    schema: dict | None = None,
    validate: bool = False,
) -> tuple[list[dict], list[tuple[str, list[str]]]]:
    """
    Load all decision files from a directory.
    
    Returns:
        (valid_decisions, errors_by_file)
    """
    decision_files = sorted(decisions_dir.glob("*.json"))
    
    valid_decisions = []
    errors_by_file = []
    
    for path in decision_files:
        decision = load_json(path)
        if decision is None:
            errors_by_file.append((path.name, ["Failed to parse JSON"]))
            continue
        
        errors = []
        
        # Schema validation
        if validate and schema:
            errors.extend(validate_decision(decision, schema))
        
        # Filename consistency check
        expected_filename = decision.get("guideline_id", "").replace(" ", "_") + ".json"
        if path.name != expected_filename:
            errors.append(
                f"Filename mismatch: file is '{path.name}' but guideline_id suggests '{expected_filename}'"
            )
        
        if errors:
            errors_by_file.append((path.name, errors))
        else:
            valid_decisions.append(decision)
    
    return valid_decisions, errors_by_file


def check_duplicate_search_ids(decisions: list[dict]) -> dict[str, list[str]]:
    """
    Check for duplicate search IDs with context-aware rules.
    
    Rules:
    1. search-fls-deep UUIDs MAY be shared between all_rust and safe_rust 
       contexts within the SAME guideline (the deep search is guideline-specific)
    2. All other search UUIDs (search-fls, etc.) must be unique per context
    3. Any UUID reuse across DIFFERENT guidelines is always flagged
    
    Supports v1.0, v1.1, v2.0, v2.1, v3.0, v3.1, v3.2, and v4.0 decision files.
    
    Returns:
        Dict mapping duplicate search_id -> list of usages that violate rules
    """
    # Track: search_id -> list of (guideline_id, context, tool)
    search_id_usage: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    
    # Per-context versions (v2.x, v3.x, v4.x)
    per_context_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    
    for decision in decisions:
        guideline_id = decision.get("guideline_id", "(unknown)")
        schema_version = decision.get("schema_version", "1.0")
        
        if schema_version in per_context_versions:
            for context in ["all_rust", "safe_rust"]:
                ctx_data = decision.get(context, {})
                search_tools = ctx_data.get("search_tools_used", [])
                
                for tool in search_tools:
                    search_id = tool.get("search_id")
                    tool_name = tool.get("tool", "unknown")
                    if search_id:
                        search_id_usage[search_id].append((guideline_id, context, tool_name))
        else:
            # v1.0, v1.1, v1.2: flat structure
            search_tools = decision.get("search_tools_used", [])
            if isinstance(search_tools, list):
                for tool in search_tools:
                    search_id = tool.get("search_id")
                    tool_name = tool.get("tool", "unknown")
                    if search_id:
                        search_id_usage[search_id].append((guideline_id, "v1", tool_name))
    
    duplicates = {}
    
    for search_id, usages in search_id_usage.items():
        if len(usages) <= 1:
            continue
        
        # Get unique guidelines that use this search_id
        guidelines = set(u[0] for u in usages)
        
        if len(guidelines) > 1:
            # Rule 3: Used by multiple different guidelines - always a violation
            duplicates[search_id] = [f"{g}:{c}" for g, c, t in usages]
        else:
            # Same guideline, check if it's search-fls-deep (allowed) or other (violation)
            tools_used = set(u[2] for u in usages)
            
            # Only search-fls-deep is allowed to be shared across contexts
            if tools_used != {"search-fls-deep"}:
                # At least one non-deep search is sharing this UUID - violation
                duplicates[search_id] = [f"{g}:{c} ({t})" for g, c, t in usages]
    
    return duplicates


def validate_paragraph_counts(ctx_data: dict, context_name: str, guideline_id: str) -> list[str]:
    """
    Validate paragraph_match_count and section_match_count match actual matches.
    
    Returns list of warning messages (empty if valid).
    """
    warnings = []
    
    if not ctx_data or ctx_data.get("decision") is None:
        return warnings  # Scaffolded context, skip validation
    
    matches = ctx_data.get("accepted_matches", [])
    actual_para, actual_section = count_matches_by_category(matches)
    
    stored_para = ctx_data.get("paragraph_match_count")
    stored_section = ctx_data.get("section_match_count")
    
    if stored_para is not None and stored_para != actual_para:
        warnings.append(
            f"{guideline_id} {context_name}: paragraph_match_count={stored_para} but actual={actual_para}"
        )
    
    if stored_section is not None and stored_section != actual_section:
        warnings.append(
            f"{guideline_id} {context_name}: section_match_count={stored_section} but actual={actual_section}"
        )
    
    return warnings


def merge_decisions_into_report(
    report: dict,
    decisions: list[dict],
) -> tuple[int, int, list[str], dict, list[tuple[str, list[str]]], list[str]]:
    """
    Merge v2.0/v2.1/v3.0/v3.1/v3.2/v4.0 decisions into a batch report.
    
    Preserves misra_add6_snapshot from v2.1+ decision files and validates
    against the batch report's misra_add6 block. Validates paragraph counts
    for v3.2/v4.0 decisions.
    
    Returns:
        (merged_count, skipped_count, skipped_guidelines, context_counts, add6_mismatches, paragraph_warnings)
    """
    merged_count = 0
    skipped_count = 0
    skipped_guidelines = []
    add6_mismatches = []
    paragraph_warnings = []
    
    # Per-context counts
    all_rust_merged = 0
    safe_rust_merged = 0
    
    # Per-context versions (v2.x, v3.x, v4.x)
    per_context_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    add6_versions = ("2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    paragraph_versions = ("3.2", "4.0")  # Versions with paragraph coverage fields
    
    # Track existing applicability changes by (guideline_id, context, field)
    existing_changes = {
        (c["guideline_id"], c.get("context", "shared"), c["field"]): i
        for i, c in enumerate(report.get("applicability_changes", []))
    }
    
    for decision in decisions:
        guideline_id = decision.get("guideline_id")
        if not guideline_id:
            skipped_count += 1
            skipped_guidelines.append("(missing guideline_id)")
            continue
        
        # Find guideline in report
        idx = find_guideline_index(report, guideline_id)
        if idx is None:
            skipped_count += 1
            skipped_guidelines.append(guideline_id)
            continue
        
        schema_version = decision.get("schema_version", "1.0")
        
        if schema_version in per_context_versions:
            # Merge per-context decisions
            verification_decision = {
                "all_rust": decision.get("all_rust", {}),
                "safe_rust": decision.get("safe_rust", {}),
            }
            
            # Count which contexts have decisions
            if verification_decision["all_rust"].get("decision"):
                all_rust_merged += 1
            if verification_decision["safe_rust"].get("decision"):
                safe_rust_merged += 1
            
            # Validate paragraph counts for v3.2/v4.0
            if schema_version in paragraph_versions:
                for ctx in ["all_rust", "safe_rust"]:
                    ctx_data = decision.get(ctx, {})
                    warnings = validate_paragraph_counts(ctx_data, ctx, guideline_id)
                    paragraph_warnings.extend(warnings)
            
            # Handle proposed changes from each context
            for context in ["all_rust", "safe_rust"]:
                ctx_data = decision.get(context, {})
                proposed_change = ctx_data.get("proposed_change")
                
                if proposed_change:
                    change_entry = {
                        "guideline_id": guideline_id,
                        "context": context,
                        "field": proposed_change["field"],
                        "current_value": proposed_change["current_value"],
                        "proposed_value": proposed_change["proposed_value"],
                        "rationale": proposed_change["rationale"],
                        "approved": None,
                    }
                    
                    key = (guideline_id, context, proposed_change["field"])
                    if key in existing_changes:
                        report["applicability_changes"][existing_changes[key]] = change_entry
                    else:
                        if "applicability_changes" not in report:
                            report["applicability_changes"] = []
                        report["applicability_changes"].append(change_entry)
                        existing_changes[key] = len(report["applicability_changes"]) - 1
            
            # Check ADD-6 snapshot consistency for v2.1+
            if schema_version in add6_versions:
                decision_add6 = decision.get("misra_add6_snapshot")
                report_add6 = report["guidelines"][idx].get("misra_add6")
                
                if decision_add6 and report_add6:
                    mismatches = check_add6_mismatch(decision_add6, report_add6)
                    if mismatches:
                        add6_mismatches.append((guideline_id, mismatches))
        else:
            # v1.0, v1.1, v1.2: convert flat structure to per-context for the report
            # Both contexts get the same decision
            ctx_decision = {
                "decision": decision.get("decision"),
                "rationale_type": decision.get("fls_rationale_type"),
                "confidence": decision.get("confidence"),
                "accepted_matches": decision.get("accepted_matches", []),
                "rejected_matches": decision.get("rejected_matches", []),
                "search_tools_used": decision.get("search_tools_used", []),
                "notes": decision.get("notes"),
            }
            
            # Add paragraph fields if present (v1.2)
            if "paragraph_match_count" in decision:
                ctx_decision["paragraph_match_count"] = decision.get("paragraph_match_count")
                ctx_decision["section_match_count"] = decision.get("section_match_count")
                ctx_decision["paragraph_level_waiver"] = decision.get("paragraph_level_waiver")
            
            verification_decision = {
                "all_rust": ctx_decision.copy(),
                "safe_rust": ctx_decision.copy(),
            }
            
            if decision.get("decision"):
                all_rust_merged += 1
                safe_rust_merged += 1
        
        # Update guideline in report
        report["guidelines"][idx]["verification_decision"] = verification_decision
        merged_count += 1
    
    context_counts = {
        "all_rust_merged": all_rust_merged,
        "safe_rust_merged": safe_rust_merged,
    }
    
    return merged_count, skipped_count, skipped_guidelines, context_counts, add6_mismatches, paragraph_warnings


def main():
    parser = argparse.ArgumentParser(
        description="Merge v2 per-guideline decision files into a batch report"
    )
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Batch number - auto-resolves paths to cache/verification/{standard}/",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Session number (required with --batch)",
    )
    parser.add_argument(
        "--batch-report",
        type=str,
        default=None,
        help="Path to the batch report JSON file (use --batch instead when possible)",
    )
    parser.add_argument(
        "--decisions-dir",
        type=str,
        default=None,
        help="Path to the decisions directory (use --batch instead when possible)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate decision files against schema before merging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be merged without writing to file",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Determine paths
    use_batch_mode = args.batch is not None
    use_explicit_mode = args.batch_report is not None or args.decisions_dir is not None
    
    if use_batch_mode and use_explicit_mode:
        print("ERROR: Cannot mix --batch with --batch-report/--decisions-dir", file=sys.stderr)
        sys.exit(1)
    
    if not use_batch_mode and not use_explicit_mode:
        print("ERROR: Either --batch or --batch-report/--decisions-dir must be provided", file=sys.stderr)
        sys.exit(1)
    
    if use_batch_mode:
        if args.session is None:
            print("ERROR: --session is required with --batch", file=sys.stderr)
            sys.exit(1)
        report_path = get_batch_report_path(root, args.standard, args.batch, args.session)
        decisions_dir = get_batch_decisions_dir(root, args.standard, args.batch)
    else:
        if args.batch_report is None or args.decisions_dir is None:
            print("ERROR: Both --batch-report and --decisions-dir are required in explicit mode", file=sys.stderr)
            sys.exit(1)
        
        try:
            report_path = resolve_path(Path(args.batch_report))
            report_path = validate_path_in_project(report_path, root)
            
            decisions_dir = resolve_path(Path(args.decisions_dir))
            decisions_dir = validate_path_in_project(decisions_dir, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Check paths exist
    if not report_path.exists():
        print(f"ERROR: Batch report not found: {report_path}", file=sys.stderr)
        sys.exit(1)
    
    if not decisions_dir.exists():
        print(f"ERROR: Decisions directory not found: {decisions_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Load batch report
    report = load_json(report_path)
    if report is None:
        print(f"ERROR: Failed to parse batch report: {report_path}", file=sys.stderr)
        sys.exit(1)
    
    report_version = report.get("schema_version", "1.0")
    print(f"Batch report schema: {report_version}")
    
    # Load schema for validation
    schema = None
    if args.validate:
        schema = load_decision_schema(root)
        if schema is None:
            print("WARNING: Decision file schema not found, skipping validation", file=sys.stderr)
    
    # Load decision files
    print(f"Loading decision files from {decisions_dir}...")
    decisions, errors_by_file = load_decision_files(decisions_dir, schema, args.validate)
    
    if errors_by_file:
        print(f"\nValidation errors in {len(errors_by_file)} file(s):", file=sys.stderr)
        for filename, errors in errors_by_file[:5]:
            print(f"  {filename}:", file=sys.stderr)
            for error in errors:
                print(f"    - {error}", file=sys.stderr)
        if len(errors_by_file) > 5:
            print(f"  ... and {len(errors_by_file) - 5} more files with errors", file=sys.stderr)
        
        if args.validate:
            print("\nERROR: Validation failed. Fix errors and retry.", file=sys.stderr)
            sys.exit(1)
        else:
            print("\nWARNING: Proceeding with valid files only.", file=sys.stderr)
    
    if not decisions:
        print("No valid decision files found.")
        sys.exit(0)
    
    # Count decision file versions
    version_counts = defaultdict(int)
    for d in decisions:
        version = d.get("schema_version", "1.0")
        version_counts[version] += 1
    
    version_info = ", ".join(f"v{v}: {c}" for v, c in sorted(version_counts.items()))
    print(f"Found {len(decisions)} valid decision file(s) ({version_info})")
    
    # Check for duplicate search IDs (validation should now happen at record time,
    # but we keep this as a safety net)
    duplicates = check_duplicate_search_ids(decisions)
    if duplicates:
        print("\nERROR: Duplicate search IDs detected:", file=sys.stderr)
        for search_id, usages in list(duplicates.items())[:5]:
            print(f"  UUID {search_id[:8]}... used by: {', '.join(usages)}", file=sys.stderr)
        if len(duplicates) > 5:
            print(f"  ... and {len(duplicates) - 5} more duplicates", file=sys.stderr)
        print("\nEach search execution can only be claimed by one guideline.", file=sys.stderr)
        print("\nUUID validation should happen at record-decision time.", file=sys.stderr)
        print("Delete the invalid decision files and re-record with proper search protocol.", file=sys.stderr)
        sys.exit(1)
    
    # Merge decisions
    print(f"\nMerging decisions into batch report...")
    merged_count, skipped_count, skipped_guidelines, context_counts, add6_mismatches, paragraph_warnings = merge_decisions_into_report(
        report, decisions
    )
    
    # Report paragraph count warnings
    if paragraph_warnings:
        print(f"\nWARNING: Paragraph count mismatches for {len(paragraph_warnings)} context(s):", file=sys.stderr)
        for warning in paragraph_warnings[:10]:
            print(f"  {warning}", file=sys.stderr)
        if len(paragraph_warnings) > 10:
            print(f"  ... and {len(paragraph_warnings) - 10} more", file=sys.stderr)
    
    # Report ADD-6 mismatches as warnings
    if add6_mismatches:
        print(f"\nWARNING: ADD-6 data mismatch for {len(add6_mismatches)} guideline(s):", file=sys.stderr)
        print("  (decision snapshot differs from batch report)", file=sys.stderr)
        for gid, diffs in add6_mismatches[:5]:
            print(f"  {gid}:", file=sys.stderr)
            for diff in diffs[:2]:
                print(f"    {diff}", file=sys.stderr)
        if len(add6_mismatches) > 5:
            print(f"  ... and {len(add6_mismatches) - 5} more", file=sys.stderr)
    
    # Update summary
    update_summary_v2(report)
    
    # Report results
    print(f"\nMerge results:")
    print(f"  Guidelines merged: {merged_count}")
    print(f"  all_rust contexts merged: {context_counts['all_rust_merged']}")
    print(f"  safe_rust contexts merged: {context_counts['safe_rust_merged']}")
    
    if skipped_count > 0:
        print(f"  Skipped (not in batch): {skipped_count}")
        for gid in skipped_guidelines[:5]:
            print(f"    - {gid}")
    
    # Report applicability changes
    changes = report.get("applicability_changes", [])
    pending_changes = [c for c in changes if c.get("approved") is None]
    if pending_changes:
        print(f"\nApplicability changes proposed: {len(pending_changes)}")
        for c in pending_changes[:5]:
            ctx = c.get("context", "shared")
            print(f"  - {c['guideline_id']} ({ctx}): {c['field']}: {c['current_value']} -> {c['proposed_value']}")
        if len(pending_changes) > 5:
            print(f"  ... and {len(pending_changes) - 5} more")
    
    # Summary
    summary = report.get("summary", {})
    total = summary.get("total_guidelines", 0)
    ar = summary.get("all_rust_verified_count", 0)
    sr = summary.get("safe_rust_verified_count", 0)
    both = summary.get("verified_count", 0)
    
    print(f"\nBatch summary:")
    print(f"  Total guidelines: {total}")
    print(f"  all_rust verified:  {ar}/{total}")
    print(f"  safe_rust verified: {sr}/{total}")
    print(f"  Both verified:      {both}/{total}")
    
    if args.dry_run:
        print(f"\n[DRY RUN] No files were modified.")
    else:
        save_json(report_path, report)
        print(f"\nUpdated: {report_path}")


if __name__ == "__main__":
    main()
