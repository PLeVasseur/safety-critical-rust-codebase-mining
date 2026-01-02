#!/usr/bin/env python3
"""
record_decision.py - Record a v3 verification decision for a guideline.

This tool records verification decisions in v3 format (per-context + ADD-6 snapshot).
Each guideline has independent decisions for all_rust and safe_rust contexts.

Features:
- Always writes v3 format decision files (includes misra_add6_snapshot)
- Single decision file per guideline contains both contexts
- Recording one context preserves the other context's data
- Validates decisions against schema
- Supports accepted and rejected matches with full metadata

Usage:
    # Record all_rust context
    uv run record-decision \\
        --standard misra-c \\
        --batch 4 \\
        --guideline "Dir 1.1" \\
        --context all_rust \\
        --decision accept_with_modifications \\
        --applicability yes \\
        --adjusted-category advisory \\
        --rationale-type direct_mapping \\
        --confidence high \\
        --search-used "uuid:search-fls-deep:Dir 1.1:5" \\
        --search-used "uuid:search-fls:query:10" \\
        --search-used "uuid:search-fls:query2:10" \\
        --search-used "uuid:search-fls:query3:10" \\
        --accept-match "fls_abc123:Section Title:0:0.65:FLS states X"

    # Then record safe_rust context (updates same file)
    uv run record-decision \\
        --standard misra-c \\
        --batch 4 \\
        --guideline "Dir 1.1" \\
        --context safe_rust \\
        --decision accept_with_modifications \\
        --applicability no \\
        --adjusted-category implicit \\
        --rationale-type rust_prevents \\
        --confidence high \\
        --search-used "uuid:search-fls-deep:Dir 1.1:5" \\
        --search-used "uuid:search-fls:safe rust:10" \\
        --search-used "uuid:search-fls:type system:10" \\
        --search-used "uuid:search-fls:borrow checker:10" \\
        --accept-match "fls_xyz:Type System:0:0.70:Rust prevents this"

Search-used format: search_id:tool:query:result_count
  - search_id: UUID4 from search tool output
  - tool: search-fls, search-fls-deep, etc.
  - query: The search query or guideline ID
  - result_count: Number of results returned

Match format: fls_id:fls_title:category:score:reason
  - fls_id: FLS identifier (e.g., fls_abc123)
  - fls_title: Human-readable title
  - category: Integer category code (0=section, -2=legality_rules, etc.)
  - score: Similarity score 0-1
  - reason: Justification text (may contain colons)

Change format: field:current_value:proposed_value:rationale
  - field: applicability, adjusted_category, or rationale_type
  - current_value: Current value
  - proposed_value: Proposed new value
  - rationale: Justification (may contain colons)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_coding_standards_dir,
    get_batch_decisions_dir,
    get_misra_rust_applicability_path,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
    VALID_STANDARDS,
    validate_search_id,
    load_valid_fls_ids,
    validate_fls_id,
    build_misra_add6_snapshot,
)


# Valid enum values from schema
VALID_DECISIONS = ["accept_with_modifications", "accept_no_matches", "accept_existing", "reject", "pending"]
VALID_CONFIDENCE = ["high", "medium", "low"]
VALID_RATIONALE_TYPES = [
    "direct_mapping",
    "partial_mapping",
    "rust_alternative",
    "rust_prevents",
    "no_equivalent",
]
VALID_CATEGORIES = [0, -1, -2, -3, -4, -5, -6, -7, -8]
VALID_CONTEXTS = ["all_rust", "safe_rust"]
VALID_APPLICABILITY = ["yes", "no", "partial"]
VALID_ADJUSTED_CATEGORIES = ["required", "advisory", "recommended", "disapplied", "implicit", "n_a"]
VALID_CHANGE_FIELDS = ["applicability", "adjusted_category", "rationale_type"]
VALID_SEARCH_TOOLS = ["search-fls", "search-fls-deep", "recompute-similarity", "read-fls-chapter", "grep-fls"]

MIN_SEARCHES_PER_CONTEXT = 4


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save a JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_decision_file_schema(root: Path) -> dict | None:
    """Load the decision file schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "decision_file.schema.json"
    if not schema_path.exists():
        return None
    return load_json(schema_path)


def guideline_id_to_filename(guideline_id: str) -> str:
    """Convert guideline ID to filename (spaces to underscores)."""
    return guideline_id.replace(" ", "_") + ".json"


def validate_decision_file(decision: dict, schema: dict) -> list[str]:
    """Validate a decision file against the schema. Returns list of errors."""
    errors = []
    try:
        jsonschema.validate(instance=decision, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation error: {e.message}")
        if e.path:
            errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema error: {e.message}")
    return errors


def parse_match(match_str: str) -> dict:
    """
    Parse a match string into a match dict.
    
    Format: fls_id:fls_title:category:score:reason
    The reason may contain colons, so we split from the left with maxsplit=4.
    """
    parts = match_str.split(":", 4)
    if len(parts) < 5:
        raise ValueError(
            f"Invalid match format: '{match_str}'. "
            f"Expected 'fls_id:fls_title:category:score:reason'"
        )
    
    fls_id, fls_title, category_str, score_str, reason = parts
    
    # Validate fls_id format
    if not fls_id.startswith("fls_"):
        raise ValueError(f"Invalid fls_id: '{fls_id}'. Must start with 'fls_'")
    
    # Parse and validate category
    try:
        category = int(category_str)
    except ValueError:
        raise ValueError(f"Invalid category: '{category_str}'. Must be an integer.")
    
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")
    
    # Parse and validate score
    try:
        score = float(score_str)
    except ValueError:
        raise ValueError(f"Invalid score: '{score_str}'. Must be a number.")
    
    if not (0 <= score <= 1):
        raise ValueError(f"Invalid score: {score}. Must be between 0 and 1.")
    
    return {
        "fls_id": fls_id,
        "fls_title": fls_title,
        "category": category,
        "score": round(score, 3),
        "reason": reason,
    }


def parse_applicability_change(change_str: str, guideline_id: str, context: str) -> dict:
    """
    Parse a v2 applicability change string.
    
    Format: field:current_value:proposed_value:rationale
    Context is provided separately via --context parameter.
    """
    parts = change_str.split(":", 3)
    if len(parts) < 4:
        raise ValueError(
            f"Invalid change format: '{change_str}'. "
            f"Expected 'field:current_value:proposed_value:rationale'"
        )
    
    field, current_value, proposed_value, rationale = parts
    
    if field not in VALID_CHANGE_FIELDS:
        raise ValueError(f"Invalid field: '{field}'. Must be one of {VALID_CHANGE_FIELDS}")
    
    return {
        "guideline_id": guideline_id,
        "context": context,
        "field": field,
        "current_value": current_value,
        "proposed_value": proposed_value,
        "rationale": rationale,
        "approved": None,  # Pending human review
    }


def parse_search_used(search_used_list: list[str]) -> list[dict]:
    """
    Parse --search-used arguments into search_tool_usage objects.
    
    Format: search_id:tool:query:result_count
      - search_id: UUID4 from search tool output (required)
      - tool: Search tool name
      - query: The search query or guideline ID
      - result_count: Number of results returned
    """
    result = []
    for item in search_used_list:
        parts = item.split(":", 3)  # Split into at most 4 parts
        
        if len(parts) < 4:
            raise ValueError(
                f"Invalid --search-used format: '{item}'. "
                f"Expected 'search_id:tool:query:result_count'"
            )
        
        search_id, tool, query, result_count_str = parts
        
        # Validate UUID format
        if not validate_search_id(search_id):
            raise ValueError(
                f"Invalid search_id: '{search_id}'. Must be a valid UUID4. "
                f"Copy the UUID from search tool output."
            )
        
        if tool not in VALID_SEARCH_TOOLS:
            raise ValueError(
                f"Invalid tool '{tool}'. Must be one of: {', '.join(VALID_SEARCH_TOOLS)}"
            )
        
        try:
            result_count = int(result_count_str)
        except ValueError:
            raise ValueError(f"Invalid result_count '{result_count_str}'. Must be integer.")
        
        result.append({
            "search_id": search_id,
            "tool": tool,
            "query": query,
            "result_count": result_count,
        })
    
    return result


def build_scaffolded_context() -> dict:
    """Build a scaffolded (empty) context decision structure."""
    return {
        "decision": None,
        "applicability": None,
        "adjusted_category": None,
        "rationale_type": None,
        "confidence": None,
        "accepted_matches": [],
        "rejected_matches": [],
        "search_tools_used": [],
        "notes": None,
    }


def build_v2_decision_file(guideline_id: str) -> dict:
    """Build a new v2 decision file with scaffolded contexts (legacy)."""
    return {
        "schema_version": "2.0",
        "guideline_id": guideline_id,
        "all_rust": build_scaffolded_context(),
        "safe_rust": build_scaffolded_context(),
        "recorded_at": None,
    }


def load_add6_data(root: Path) -> dict:
    """Load MISRA ADD-6 Rust applicability data."""
    add6_path = get_misra_rust_applicability_path(root)
    if not add6_path.exists():
        return {}
    with open(add6_path) as f:
        data = json.load(f)
    return data.get("guidelines", {})


def build_v3_decision_file(guideline_id: str, add6_snapshot: dict | None) -> dict:
    """Build a new v3 decision file with ADD-6 snapshot and scaffolded contexts."""
    return {
        "schema_version": "3.0",
        "guideline_id": guideline_id,
        "misra_add6_snapshot": add6_snapshot,
        "all_rust": build_scaffolded_context(),
        "safe_rust": build_scaffolded_context(),
        "recorded_at": None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Record a v3 verification decision for a guideline (per-context + ADD-6)"
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
        required=True,
        help="Batch number - writes to cache/verification/{standard}/batch{N}_decisions/",
    )
    parser.add_argument(
        "--guideline",
        type=str,
        required=True,
        help="Guideline ID (e.g., 'Dir 1.1', 'Rule 10.1')",
    )
    parser.add_argument(
        "--context",
        type=str,
        required=True,
        choices=VALID_CONTEXTS,
        help="Which context to record: all_rust or safe_rust",
    )
    parser.add_argument(
        "--decision",
        type=str,
        required=True,
        choices=VALID_DECISIONS,
        help="Verification decision type",
    )
    parser.add_argument(
        "--applicability",
        type=str,
        required=True,
        choices=VALID_APPLICABILITY,
        help="Whether the guideline applies in this context: yes, no, partial",
    )
    parser.add_argument(
        "--adjusted-category",
        type=str,
        required=True,
        choices=VALID_ADJUSTED_CATEGORIES,
        help="MISRA adjusted category for Rust",
    )
    parser.add_argument(
        "--rationale-type",
        type=str,
        required=True,
        choices=VALID_RATIONALE_TYPES,
        help="Type of FLS rationale",
    )
    parser.add_argument(
        "--confidence",
        type=str,
        required=True,
        choices=VALID_CONFIDENCE,
        help="Confidence level in the decision",
    )
    parser.add_argument(
        "--accept-match",
        type=str,
        action="append",
        default=[],
        dest="accept_matches",
        help="Accepted FLS match (format: fls_id:fls_title:category:score:reason). Repeatable.",
    )
    parser.add_argument(
        "--reject-match",
        type=str,
        action="append",
        default=[],
        dest="reject_matches",
        help="Rejected FLS match (format: fls_id:fls_title:category:score:reason). Repeatable.",
    )
    parser.add_argument(
        "--search-used",
        dest="search_used",
        action="append",
        default=[],
        help=f"Search tool used (format: search_id:tool:query:result_count). Repeatable. "
             f"At least {MIN_SEARCHES_PER_CONTEXT} required. Tools: {', '.join(VALID_SEARCH_TOOLS)}.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Additional notes about the decision",
    )
    parser.add_argument(
        "--propose-change",
        type=str,
        default=None,
        help="Propose change (format: field:current:proposed:rationale). Fields: applicability, adjusted_category, rationale_type",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be recorded without writing to file",
    )
    parser.add_argument(
        "--force-no-matches",
        action="store_true",
        help="Override requirement for FLS matches (requires --notes justification)",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    context = args.context
    
    # Validate guideline is in the specified batch
    from fls_tools.standards.verification.batch_check import validate_guideline_in_batch
    
    is_valid, error_msg, actual_batch = validate_guideline_in_batch(
        root, args.standard, args.guideline, args.batch
    )
    if not is_valid:
        print(f"ERROR: {error_msg}", file=sys.stderr)
        sys.exit(1)
    
    # Parse matches
    try:
        accepted_matches = [parse_match(m) for m in args.accept_matches]
        rejected_matches = [parse_match(m) for m in args.reject_matches]
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Validate FLS IDs against the known valid IDs
    valid_fls_ids = load_valid_fls_ids(root)
    if valid_fls_ids is None:
        print("WARNING: Could not load valid_fls_ids.json - FLS ID validation skipped", file=sys.stderr)
        print("  Run 'uv run generate-valid-fls-ids' to generate this file", file=sys.stderr)
    else:
        invalid_ids = []
        for match in accepted_matches + rejected_matches:
            fls_id = match["fls_id"]
            is_valid, error_msg = validate_fls_id(fls_id, valid_fls_ids)
            if not is_valid:
                invalid_ids.append((fls_id, error_msg))
        
        if invalid_ids:
            print("ERROR: Invalid FLS ID(s) detected:", file=sys.stderr)
            for fls_id, error_msg in invalid_ids:
                print(f"  - {fls_id}: {error_msg}", file=sys.stderr)
            print("\nThese FLS IDs do not exist in the FLS specification.", file=sys.stderr)
            print("Use 'uv run search-fls <query>' to find valid FLS sections.", file=sys.stderr)
            print("If you believe this is an error, run 'uv run generate-valid-fls-ids' to refresh.", file=sys.stderr)
            sys.exit(1)
    
    # Validate at least one match unless explicitly overridden
    if not accepted_matches and not rejected_matches and not args.force_no_matches:
        print(f"""ERROR: At least one --accept-match or --reject-match must be provided

Even for 'no_equivalent' or 'n_a' cases, include FLS sections that explain
WHY the concept doesn't apply to Rust.

Guidance by rationale type:
  - no_equivalent: FLS sections showing Rust lacks the C construct
  - rust_prevents: Type system, borrow checker, or ownership sections
  - rust_alternative: FLS sections describing Rust's alternative mechanism
  - partial_mapping: FLS sections that partially address the concern
  - direct_mapping: FLS sections that directly address the concern

Use --force-no-matches only for exceptional cases (requires --notes).
""", file=sys.stderr)
        sys.exit(1)
    
    if args.force_no_matches and not args.notes:
        print("ERROR: --force-no-matches requires --notes explaining why no FLS matches apply", file=sys.stderr)
        sys.exit(1)
    
    # Parse and validate search tool usage
    if not args.search_used:
        print(f"ERROR: --search-used is required (at least {MIN_SEARCHES_PER_CONTEXT} times)", file=sys.stderr)
        print("  Format: search_id:tool:query:result_count", file=sys.stderr)
        sys.exit(1)
    
    try:
        search_tools_used = parse_search_used(args.search_used)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    if len(search_tools_used) < MIN_SEARCHES_PER_CONTEXT:
        print(f"ERROR: At least {MIN_SEARCHES_PER_CONTEXT} searches required, got {len(search_tools_used)}", file=sys.stderr)
        print("  Required protocol:", file=sys.stderr)
        print("    1. search-fls-deep --guideline <id>", file=sys.stderr)
        print("    2. search-fls with C/MISRA terminology", file=sys.stderr)
        print("    3. search-fls with Rust terminology", file=sys.stderr)
        print("    4. search-fls with safety/semantic concepts", file=sys.stderr)
        sys.exit(1)
    
    # Parse proposed change if provided
    proposed_change = None
    if args.propose_change:
        try:
            proposed_change = parse_applicability_change(
                args.propose_change, args.guideline, context
            )
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Load ADD-6 data
    add6_all = load_add6_data(root)
    add6 = add6_all.get(args.guideline)
    if not add6:
        print(f"WARNING: No ADD-6 data found for {args.guideline}", file=sys.stderr)
        add6_snapshot = None
    else:
        add6_snapshot = build_misra_add6_snapshot(add6)
    
    # Determine output path
    output_dir = get_batch_decisions_dir(root, args.standard, args.batch)
    filename = guideline_id_to_filename(args.guideline)
    output_path = output_dir / filename
    
    # Load existing decision file or create new one
    if output_path.exists():
        decision_file = load_json(output_path)
        # Accept v2.0, v2.1, or v3.0 - upgrade to v3.0 if needed
        existing_version = decision_file.get("schema_version")
        if existing_version not in ("2.0", "2.1", "3.0"):
            print(f"ERROR: Existing decision file has unsupported version: {existing_version}", file=sys.stderr)
            sys.exit(1)
        # Upgrade to v3.0 if needed
        if existing_version in ("2.0", "2.1"):
            decision_file["schema_version"] = "3.0"
            if "misra_add6_snapshot" not in decision_file and add6_snapshot:
                decision_file["misra_add6_snapshot"] = add6_snapshot
    else:
        decision_file = build_v3_decision_file(args.guideline, add6_snapshot)
    
    # Build the context decision
    context_decision = {
        "decision": args.decision,
        "applicability": args.applicability,
        "adjusted_category": args.adjusted_category,
        "rationale_type": args.rationale_type,
        "confidence": args.confidence,
        "accepted_matches": accepted_matches,
        "rejected_matches": rejected_matches,
        "search_tools_used": search_tools_used,
        "notes": args.notes,
    }
    
    if proposed_change:
        context_decision["proposed_change"] = {
            "field": proposed_change["field"],
            "current_value": proposed_change["current_value"],
            "proposed_value": proposed_change["proposed_value"],
            "rationale": proposed_change["rationale"],
        }
    
    # Update the specified context
    decision_file[context] = context_decision
    decision_file["recorded_at"] = datetime.now(timezone.utc).isoformat()
    
    # Validate against schema
    schema = load_decision_file_schema(root)
    if schema:
        errors = validate_decision_file(decision_file, schema)
        if errors:
            print("WARNING: Decision file has schema validation issues:", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
            # Don't fail - schema may not be updated yet
    
    # Output
    if args.dry_run:
        print(f"DRY RUN - Would write decision file:")
        print(f"  Path: {output_path}")
        print(f"  Guideline: {args.guideline}")
        print(f"  Context: {context}")
        print(f"  Decision: {args.decision}")
        print(f"  Applicability: {args.applicability}")
        print(f"  Adjusted Category: {args.adjusted_category}")
        print(f"  Rationale Type: {args.rationale_type}")
        print(f"  Confidence: {args.confidence}")
        print(f"  Accepted Matches: {len(accepted_matches)}")
        for m in accepted_matches:
            reason_preview = m['reason'][:60] + '...' if len(m['reason']) > 60 else m['reason']
            print(f"    - {m['fls_id']} ({m['score']:.3f}): {reason_preview}")
        print(f"  Rejected Matches: {len(rejected_matches)}")
        for m in rejected_matches:
            reason_preview = m['reason'][:60] + '...' if len(m['reason']) > 60 else m['reason']
            print(f"    - {m['fls_id']} ({m['score']:.3f}): {reason_preview}")
        print(f"  Search Tools Used: {len(search_tools_used)}")
        for s in search_tools_used:
            print(f"    - [{s['search_id'][:8]}...] {s['tool']}: {s['query']} ({s['result_count']} results)")
        if args.notes:
            print(f"  Notes: {args.notes}")
        if proposed_change:
            print(f"  Proposed Change: {proposed_change['field']}: "
                  f"{proposed_change['current_value']} -> {proposed_change['proposed_value']}")
        
        # Show other context status
        other_context = "safe_rust" if context == "all_rust" else "all_rust"
        other_decision = decision_file.get(other_context, {}).get("decision")
        if other_decision:
            print(f"  Other context ({other_context}): {other_decision}")
        else:
            print(f"  Other context ({other_context}): not yet recorded")
    else:
        # Create output directory if needed
        output_dir.mkdir(parents=True, exist_ok=True)
        
        save_json(output_path, decision_file)
        
        print(f"Recorded {context} decision for {args.guideline}")
        print(f"  Output: {output_path}")
        print(f"  Decision: {args.decision}")
        print(f"  Applicability: {args.applicability}, Category: {args.adjusted_category}")
        print(f"  Rationale: {args.rationale_type}, Confidence: {args.confidence}")
        print(f"  Matches: {len(accepted_matches)} accepted, {len(rejected_matches)} rejected")
        print(f"  Searches: {len(search_tools_used)}")
        
        # Show other context status
        other_context = "safe_rust" if context == "all_rust" else "all_rust"
        other_decision = decision_file.get(other_context, {}).get("decision")
        if other_decision:
            print(f"  {other_context}: {other_decision} (already recorded)")
        else:
            print(f"  {other_context}: pending")
        
        if proposed_change:
            print(f"  Proposed change: {proposed_change['field']}: "
                  f"{proposed_change['current_value']} -> {proposed_change['proposed_value']}")


if __name__ == "__main__":
    main()
