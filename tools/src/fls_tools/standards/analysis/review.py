#!/usr/bin/env python3
"""
review-outliers - Interactive human review tool for outlier analysis.

This tool allows humans to review and make decisions on outlier analysis,
recording per-aspect and per-FLS-ID decisions (per-context) in the outlier files.

Modes:
    --interactive  Interactive prompts for each decision (batch or single)
    --show         Display LLM analysis without making decisions
    CLI flags      Direct accept/reject via command line

Usage:
    # Interactive mode for a batch (prompts for each guideline)
    uv run review-outliers --standard misra-c --batch 1

    # Interactive mode for all batches
    uv run review-outliers --standard misra-c --all

    # Resume from a specific guideline
    uv run review-outliers --standard misra-c --batch 1 --start-from "Rule 10.5"

    # Show LLM analysis for a guideline
    uv run review-outliers --standard misra-c --guideline "Rule 10.1" --show

    # Accept all aspects for a guideline
    uv run review-outliers --standard misra-c --guideline "Rule 10.1" --accept-all

    # Accept FLS removal for specific context
    uv run review-outliers --standard misra-c --guideline "Rule 10.1" \\
        --accept-removal fls_xyz123 --context all_rust --reason "Over-matched"

    # Bulk accept a systematic removal across all guidelines for a context
    uv run review-outliers --standard misra-c --bulk-accept-removal fls_xyz123 \\
        --context all_rust --reason "Over-matched in initial mapping"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_outlier_analysis_dir,
    load_outlier_analysis,
    save_outlier_analysis,
    load_review_state,
    save_review_state,
    recompute_review_summary,
    get_active_flags,
    filename_to_guideline,
    BATCH_EXPECTED_PATTERNS,
)


VALID_CONTEXTS = ["all_rust", "safe_rust", "both"]

# Investigation request marker for OpenCode integration
INVESTIGATION_REQUEST_PREFIX = "INVESTIGATION_REQUEST:"


def output_investigation_request(
    guideline_id: str,
    aspect: str,
    fls_id: str | None = None,
    context: str | None = None,
    user_guidance: str | None = None,
) -> None:
    """
    Output a structured investigation request for OpenCode to intercept.
    
    Args:
        guideline_id: The guideline being reviewed (e.g., "Dir 4.3")
        aspect: The aspect to investigate ("fls_removal", "fls_addition", "categorization", 
                "specificity", "add6_divergence", "all")
        fls_id: Optional FLS ID for FLS-specific investigations
        context: Optional context for context-specific investigations ("all_rust", "safe_rust")
        user_guidance: Optional natural language guidance from the user
    """
    import json
    request = {
        "guideline_id": guideline_id,
        "aspect": aspect,
    }
    if fls_id:
        request["fls_id"] = fls_id
    if context:
        request["context"] = context
    if user_guidance:
        request["user_guidance"] = user_guidance
    
    print(f"\n{INVESTIGATION_REQUEST_PREFIX}{json.dumps(request)}")
    print("\nInvestigation requested. Perform investigation and press Enter when complete...")
    print("(Or press 'c' then Enter to cancel)")


def wait_for_investigation_completion() -> bool:
    """
    Wait for user to signal that investigation is complete.
    
    Returns True if investigation was completed, False if cancelled.
    """
    try:
        response = input("\nPress Enter when investigation is complete (or 'c' to cancel) > ").strip().lower()
        if response in ("c", "cancel"):
            print("Investigation cancelled.")
            return False
        return True
    except (EOFError, KeyboardInterrupt):
        print("\nInvestigation cancelled.")
        return False


def is_investigate_response(response: str | tuple) -> tuple[bool, str | None]:
    """
    Check if a prompt response is an investigate request.
    
    Args:
        response: Either a string or a tuple from a prompt function
    
    Returns:
        (is_investigate, user_guidance) tuple
    """
    if isinstance(response, tuple) and len(response) == 2 and response[0] in ("investigate", "investigate_all"):
        return (True, response[1])
    return (False, None)


def parse_investigate_command(response: str) -> tuple[bool, str | None]:
    """
    Parse an investigate command, extracting optional quoted guidance.
    
    Args:
        response: The user's input (e.g., 'i', 'i "some guidance"', 'investigate "guidance"')
    
    Returns:
        (is_investigate, user_guidance) tuple.
        is_investigate is True if this is an investigate command.
        user_guidance is the quoted string if provided, else None.
    
    Examples:
        'i' -> (True, None)
        'i "check encapsulation"' -> (True, "check encapsulation")
        'investigate "look at X"' -> (True, "look at X")
        'y' -> (False, None)
    """
    import re
    
    response = response.strip()
    
    # Check if starts with i or investigate
    if not response.lower().startswith(("i ", "i\"", "investigate")) and response.lower() not in ("i", "investigate"):
        return (False, None)
    
    # It's an investigate command - extract optional guidance
    # Pattern: i or investigate followed by optional quoted string
    match = re.match(r'^(?:i|investigate)\s*"([^"]*)"?\s*$', response, re.IGNORECASE)
    if match:
        return (True, match.group(1))
    
    # Check for simple i or investigate without quotes
    if response.lower() in ("i", "investigate"):
        return (True, None)
    
    # i followed by something but not in quotes - treat as guidance anyway
    match = re.match(r'^(?:i|investigate)\s+(.+)$', response, re.IGNORECASE)
    if match:
        guidance = match.group(1).strip()
        # Remove surrounding quotes if present
        if guidance.startswith('"') and guidance.endswith('"'):
            guidance = guidance[1:-1]
        elif guidance.startswith("'") and guidance.endswith("'"):
            guidance = guidance[1:-1]
        return (True, guidance if guidance else None)
    
    return (True, None)


def display_investigation_findings(analysis: dict, aspect: str | None = None, fls_id: str | None = None, context: str | None = None) -> bool:
    """
    Display investigation findings from the outlier analysis file.
    
    Args:
        analysis: The full outlier analysis data
        aspect: Optional filter by aspect type
        fls_id: Optional filter by FLS ID
        context: Optional filter by context
    
    Returns True if any findings were displayed.
    """
    investigations = analysis.get("llm_investigation", {}).get("investigations", [])
    if not investigations:
        return False
    
    # Filter investigations
    filtered = investigations
    if aspect:
        filtered = [inv for inv in filtered if inv.get("aspect") == aspect]
    if fls_id:
        filtered = [inv for inv in filtered if inv.get("target", {}).get("fls_id") == fls_id]
    if context:
        filtered = [inv for inv in filtered if inv.get("target", {}).get("context") == context]
    
    if not filtered:
        return False
    
    print("\n" + "─" * 60)
    print("INVESTIGATION FINDINGS")
    print("─" * 60)
    
    for inv in filtered:
        timestamp = inv.get("timestamp", "Unknown time")
        inv_aspect = inv.get("aspect", "unknown")
        target = inv.get("target", {})
        findings = inv.get("findings", {})
        
        target_str = ""
        if target.get("fls_id"):
            target_str = f" - {target['fls_id']}"
            if target.get("context"):
                target_str += f" ({target['context']})"
        
        print(f"\n[{timestamp}] {inv_aspect}{target_str}")
        print(f"  Sources: {', '.join(inv.get('sources_consulted', []))[:80]}...")
        
        if findings.get("fls_content_summary"):
            print(f"  FLS Content: {findings['fls_content_summary'][:100]}...")
        if findings.get("relevance_assessment"):
            print(f"  Relevance: {findings['relevance_assessment'][:100]}...")
        if findings.get("recommendation"):
            confidence = findings.get("confidence", "unknown")
            print(f"  Recommendation: {findings['recommendation']} (confidence: {confidence})")
    
    print("─" * 60)
    return True


def create_human_review_section() -> dict:
    """Create initial human_review section structure."""
    return {
        "overall_status": "pending",
        "reviewed_at": None,
        "categorization": None,
        "fls_removals": {},  # {fls_id: {contexts: [...], decisions: {ctx: {decision, reason}}}}
        "fls_additions": {},
        "add6_divergence": None,
        "specificity": None,
        "notes": None,
    }


def compute_overall_status(human_review: dict, flags: dict, llm_analysis: dict) -> str:
    """
    Compute overall review status based on individual decisions.
    
    Returns 'fully_reviewed', 'partial', or 'pending'.
    """
    pending_aspects = 0
    total_aspects = 0
    
    # Check categorization if relevant flags set - now per-context
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        cat = human_review.get("categorization")
        if cat is None:
            cat = {}
        # Handle both old format (single decision) and new format (per-context)
        if isinstance(cat, dict) and cat.get("decision"):
            # Old format - single decision applies to both contexts
            pass  # Already decided
        else:
            # New format - per-context decisions
            for ctx in ["all_rust", "safe_rust"]:
                total_aspects += 1
                ctx_cat = cat.get(ctx) if isinstance(cat, dict) else None
                if not ctx_cat or not ctx_cat.get("decision"):
                    pending_aspects += 1
    
    # Check FLS removals - need per-context decisions
    for fls_id, item in human_review.get("fls_removals", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            total_aspects += 1
            if not decisions.get(ctx, {}).get("decision"):
                pending_aspects += 1
    
    # Check FLS additions - need per-context decisions
    for fls_id, item in human_review.get("fls_additions", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            total_aspects += 1
            if not decisions.get(ctx, {}).get("decision"):
                pending_aspects += 1
    
    # Check ADD-6 divergence
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        total_aspects += 1
        if not human_review.get("add6_divergence"):
            pending_aspects += 1
    
    # Check specificity if flag set
    if flags.get("specificity_decreased"):
        total_aspects += 1
        if not human_review.get("specificity"):
            pending_aspects += 1
    
    if total_aspects == 0:
        return "fully_reviewed"
    if pending_aspects == 0:
        return "fully_reviewed"
    if pending_aspects < total_aspects:
        return "partial"
    return "pending"


def display_llm_analysis(analysis: dict) -> None:
    """Display LLM analysis in a readable format."""
    llm = analysis.get("llm_analysis", {})
    if not llm:
        print("  No LLM analysis recorded.")
        return
    
    print(f"\n{'='*60}")
    print(f"LLM ANALYSIS: {analysis.get('guideline_id')}")
    print(f"{'='*60}")
    
    print(f"\nOverall Recommendation: {llm.get('overall_recommendation', 'N/A')}")
    print(f"\nSummary:\n  {llm.get('summary', 'N/A')}")
    
    # Categorization (supports both old single-verdict and new per-context format)
    cat = llm.get("categorization")
    if cat:
        print(f"\n--- Categorization ---")
        # Check if it's the new per-context format
        if cat.get("all_rust") is not None or cat.get("safe_rust") is not None:
            # New per-context format
            for ctx in ["all_rust", "safe_rust"]:
                ctx_cat = cat.get(ctx)
                if ctx_cat:
                    print(f"  {ctx}:")
                    print(f"    Verdict: {ctx_cat.get('verdict')}")
                    print(f"    Reasoning: {ctx_cat.get('reasoning')}")
        else:
            # Old single-verdict format
            print(f"  Verdict: {cat.get('verdict')}")
            print(f"  Reasoning: {cat.get('reasoning')}")
    
    # FLS Removals
    removals = llm.get("fls_removals")
    if removals:
        print(f"\n--- FLS Removals ---")
        print(f"  Verdict: {removals.get('verdict')}")
        print(f"  Reasoning: {removals.get('reasoning')}")
        per_id = removals.get("per_id", {})
        if per_id:
            print(f"  Per-ID:")
            for fls_id, info in per_id.items():
                contexts = info.get("contexts", [])
                print(f"    {fls_id} (contexts: {', '.join(contexts)}):")
                print(f"      Title: {info.get('title')}")
                print(f"      Category: {info.get('category')}")
                orig = info.get('original_reason', 'N/A') or 'N/A'
                print(f"      Original reason: {orig[:100]}...")
                decisions = info.get("removal_decisions", {})
                for ctx, justification in decisions.items():
                    print(f"      LLM justification ({ctx}): {justification}")
    
    # FLS Additions
    additions = llm.get("fls_additions")
    if additions:
        print(f"\n--- FLS Additions ---")
        print(f"  Verdict: {additions.get('verdict')}")
        print(f"  Reasoning: {additions.get('reasoning')}")
        per_id = additions.get("per_id", {})
        if per_id:
            print(f"  Per-ID:")
            for fls_id, info in per_id.items():
                contexts = info.get("contexts", [])
                print(f"    {fls_id} (contexts: {', '.join(contexts)}):")
                print(f"      Title: {info.get('title')}")
                print(f"      Category: {info.get('category')}")
                new_reason = info.get('new_reason', 'N/A') or 'N/A'
                print(f"      New reason: {new_reason[:100]}...")
                decisions = info.get("addition_decisions", {})
                for ctx, justification in decisions.items():
                    print(f"      LLM justification ({ctx}): {justification}")
    
    # ADD-6 Divergence - always show if divergence flags are set or analysis exists
    add6_analysis = llm.get("add6_divergence")
    flags = analysis.get("flags", {})
    has_divergence_flag = flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6")
    
    if add6_analysis or has_divergence_flag:
        print(f"\n--- ADD-6 Divergence ---")
        
        # Show per-context comparison
        add6_data = analysis.get("add6", {})
        comparison = analysis.get("comparison", {})
        mapping = analysis.get("enriched_matches", {}).get("mapping", {})
        decision = analysis.get("enriched_matches", {}).get("decision", {})
        
        print(f"  Per-context comparison:")
        for ctx in ["all_rust", "safe_rust"]:
            add6_key = f"applicability_{ctx}"
            add6_app = add6_data.get(add6_key, "N/A")
            
            # Get decision applicability - try multiple sources
            ctx_comp = comparison.get(ctx, {})
            # The decision applicability might be in different places depending on data structure
            # Check comparison data first, then look at the decision matches
            dec_app = "N/A"
            if ctx_comp:
                # Try to infer from the comparison - if applicability_changed is false, it matches mapping
                if not ctx_comp.get("applicability_changed", True):
                    # No change means decision = mapping
                    dec_app = "(unchanged)"
                else:
                    trans = ctx_comp.get("applicability_mapping_to_decision")
                    if trans:
                        # Format is "old→new"
                        dec_app = trans.split("→")[-1] if "→" in trans else trans
            
            diverges = ctx_comp.get("applicability_differs_from_add6", False)
            status = "✗ DIVERGES" if diverges else "✓"
            print(f"    {ctx}: ADD-6={add6_app}, Decision={dec_app} {status}")
        
        if add6_analysis:
            print(f"  Verdict: {add6_analysis.get('verdict')}")
            print(f"  Reasoning: {add6_analysis.get('reasoning')}")
        else:
            print(f"  Verdict: (not analyzed)")
            print(f"  WARNING: Divergence flags are set but no analysis recorded!")
    
    # Specificity
    spec = llm.get("specificity")
    if spec:
        print(f"\n--- Specificity ---")
        print(f"  Verdict: {spec.get('verdict')}")
        print(f"  Reasoning: {spec.get('reasoning')}")
        lost = spec.get("lost_paragraphs", [])
        if lost:
            print(f"  Lost paragraphs:")
            for p in lost[:5]:  # Limit display
                print(f"    - {p.get('fls_id')} ({p.get('fls_title')})")
    
    # Routine pattern
    if llm.get("routine_pattern"):
        print(f"\nRoutine Pattern: {llm.get('routine_pattern')}")
    
    # Notes
    if llm.get("notes"):
        print(f"\nNotes: {llm.get('notes')}")
    
    print(f"\n{'='*60}")


def display_pending_decisions(analysis: dict) -> None:
    """Display what decisions still need to be made."""
    human_review = analysis.get("human_review")
    if not human_review:
        print("  No human review started yet.")
        return
    
    flags = analysis.get("flags", {})
    active = get_active_flags(flags)
    
    print(f"\nActive flags: {', '.join(active) if active else 'None'}")
    print(f"Overall status: {human_review.get('overall_status')}")
    
    pending = []
    
    # Check categorization - now per-context
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        cat = human_review.get("categorization")
        if cat is None:
            cat = {}
        # Handle both old format (single decision) and new format (per-context)
        if isinstance(cat, dict) and cat.get("decision"):
            # Old format - already decided
            pass
        else:
            for ctx in ["all_rust", "safe_rust"]:
                ctx_cat = cat.get(ctx) if isinstance(cat, dict) else None
                if not ctx_cat or not ctx_cat.get("decision"):
                    pending.append(f"categorization:{ctx}")
    
    # Check FLS removals
    for fls_id, item in human_review.get("fls_removals", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            if not decisions.get(ctx, {}).get("decision"):
                pending.append(f"fls_removal:{fls_id}:{ctx}")
    
    # Check FLS additions
    for fls_id, item in human_review.get("fls_additions", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            if not decisions.get(ctx, {}).get("decision"):
                pending.append(f"fls_addition:{fls_id}:{ctx}")
    
    # Check ADD-6 divergence
    if (flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6")) and not human_review.get("add6_divergence"):
        pending.append("add6_divergence")
    
    # Check specificity
    if flags.get("specificity_decreased") and not human_review.get("specificity"):
        pending.append("specificity")
    
    if pending:
        print(f"\nPending decisions ({len(pending)}):")
        for p in pending:
            print(f"  - {p}")
    else:
        print("\nAll decisions complete!")


def initialize_fls_structures(human_review: dict, llm_analysis: dict, comparison: dict) -> None:
    """
    Initialize FLS removal/addition structures from LLM analysis or comparison data.
    
    Uses per-context structure: {fls_id: {contexts: [...], decisions: {ctx: {decision, reason}}}}
    """
    # Initialize from LLM analysis per_id (if available)
    llm_removals = llm_analysis.get("fls_removals", {}).get("per_id", {})
    llm_additions = llm_analysis.get("fls_additions", {}).get("per_id", {})
    
    # FLS Removals
    for fls_id, info in llm_removals.items():
        if fls_id not in human_review["fls_removals"]:
            human_review["fls_removals"][fls_id] = {
                "contexts": info.get("contexts", []),
                "title": info.get("title"),
                "category": info.get("category"),
                "decisions": {},
            }
    
    # Also check comparison data for any missing
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        for fls_id in ctx_comp.get("fls_removed", []):
            if fls_id not in human_review["fls_removals"]:
                human_review["fls_removals"][fls_id] = {
                    "contexts": [ctx],
                    "title": None,
                    "category": None,
                    "decisions": {},
                }
            elif ctx not in human_review["fls_removals"][fls_id]["contexts"]:
                human_review["fls_removals"][fls_id]["contexts"].append(ctx)
    
    # FLS Additions
    for fls_id, info in llm_additions.items():
        if fls_id not in human_review["fls_additions"]:
            human_review["fls_additions"][fls_id] = {
                "contexts": info.get("contexts", []),
                "title": info.get("title"),
                "category": info.get("category"),
                "decisions": {},
            }
    
    # Also check comparison data
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        for fls_id in ctx_comp.get("fls_added", []):
            if fls_id not in human_review["fls_additions"]:
                human_review["fls_additions"][fls_id] = {
                    "contexts": [ctx],
                    "title": None,
                    "category": None,
                    "decisions": {},
                }
            elif ctx not in human_review["fls_additions"][fls_id]["contexts"]:
                human_review["fls_additions"][fls_id]["contexts"].append(ctx)


def apply_fls_decision(
    human_review: dict,
    fls_dict: dict,
    fls_id: str,
    context: str,
    decision: str,
    reason: str | None,
) -> bool:
    """
    Apply a decision to an FLS ID for a specific context.
    
    Returns True if successful, False if FLS ID or context not found.
    """
    if fls_id not in fls_dict:
        return False
    
    item = fls_dict[fls_id]
    contexts = item.get("contexts", [])
    
    if context == "both":
        # Apply to all contexts where this FLS ID appears
        for ctx in contexts:
            if "decisions" not in item:
                item["decisions"] = {}
            item["decisions"][ctx] = {"decision": decision, "reason": reason}
        return True
    elif context in contexts:
        if "decisions" not in item:
            item["decisions"] = {}
        item["decisions"][context] = {"decision": decision, "reason": reason}
        return True
    else:
        return False


# =============================================================================
# Interactive Mode Functions
# =============================================================================

def get_guidelines_for_batch(batch: int, root: Path) -> list[str]:
    """Get all guideline IDs in a specific batch, sorted."""
    outlier_dir = get_outlier_analysis_dir(root)
    guidelines = []
    
    import json
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("batch") == batch:
                guidelines.append(data.get("guideline_id"))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(guidelines)


def get_all_guidelines(root: Path) -> list[tuple[int, str]]:
    """Get all (batch, guideline_id) pairs, sorted by batch then guideline."""
    outlier_dir = get_outlier_analysis_dir(root)
    guidelines = []
    
    import json
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            batch = data.get("batch", 0)
            guideline_id = data.get("guideline_id")
            if guideline_id:
                guidelines.append((batch, guideline_id))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(guidelines)


def get_pending_guidelines(root: Path, batch: int | None = None) -> list[str]:
    """Get guidelines that haven't been fully reviewed yet."""
    outlier_dir = get_outlier_analysis_dir(root)
    pending = []
    
    import json
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if batch is not None and data.get("batch") != batch:
                continue
            human_review = data.get("human_review")
            if human_review is None or human_review.get("overall_status") != "fully_reviewed":
                pending.append(data.get("guideline_id"))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(pending)


def prompt_yes_no_skip_quit(prompt: str, show_help: bool = True, allow_investigate: bool = False) -> str | tuple[str, str | None]:
    """
    Prompt user for y/n/s/q response.
    
    Returns: 
        - 'yes', 'no', 'skip', 'quit', 'help' as strings
        - ('investigate', user_guidance) tuple when investigate is chosen
          user_guidance may be None or a string with optional guidance
    """
    help_text = " | [?] help" if show_help else ""
    investigate_text = ' | [i]nvestigate or i "guidance"' if allow_investigate else ""
    while True:
        try:
            response = input(f"{prompt} [y]es | [n]o | [s]kip{investigate_text}{help_text} | [q]uit > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        response_lower = response.lower()
        
        if response_lower in ("y", "yes"):
            return "yes"
        elif response_lower in ("n", "no"):
            return "no"
        elif response_lower in ("s", "skip"):
            return "skip"
        elif response_lower in ("q", "quit"):
            return "quit"
        elif response_lower == "?" and show_help:
            return "help"
        elif allow_investigate:
            is_investigate, user_guidance = parse_investigate_command(response)
            if is_investigate:
                return ("investigate", user_guidance)
        
        valid_parts = ["y", "n", "s"]
        if allow_investigate:
            valid_parts.append('i or i "guidance"')
        if show_help:
            valid_parts.append("?")
        valid_parts.append("q")
        print(f"  Invalid input. Please enter {', '.join(valid_parts)}.")


def prompt_yes_no_na(prompt: str, allow_na: bool = True, show_help: bool = True, allow_investigate: bool = False) -> str | tuple[str, str | None]:
    """
    Prompt user for y/n/n_a response.
    
    Returns:
        - 'yes', 'no', 'n_a', 'quit', 'help' as strings
        - ('investigate', user_guidance) tuple when investigate is chosen
    """
    na_text = " | [n/a]" if allow_na else ""
    help_text = " | [?] help" if show_help else ""
    investigate_text = ' | [i]nvestigate or i "guidance"' if allow_investigate else ""
    while True:
        try:
            response = input(f"{prompt} [y]es | [n]o{na_text}{investigate_text}{help_text} > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        response_lower = response.lower()
        
        if response_lower in ("y", "yes"):
            return "yes"
        elif response_lower in ("n", "no"):
            return "no"
        elif allow_na and response_lower in ("na", "n/a", "n_a"):
            return "n_a"
        elif response_lower in ("q", "quit"):
            return "quit"
        elif response_lower == "?" and show_help:
            return "help"
        elif allow_investigate:
            is_investigate, user_guidance = parse_investigate_command(response)
            if is_investigate:
                return ("investigate", user_guidance)
        
        valid_parts = ["y", "n"]
        if allow_na:
            valid_parts.append("n/a")
        if allow_investigate:
            valid_parts.append('i or i "guidance"')
        if show_help:
            valid_parts.append("?")
        valid_parts.append("q")
        print(f"  Invalid input. Please enter {', '.join(valid_parts)}.")


def prompt_accept_all(prompt: str) -> str:
    """
    Prompt user for accept-all option.
    
    Returns: 'yes', 'no', 'all', or 'quit'
    """
    while True:
        try:
            response = input(f"{prompt} [y]es | [n]o | [a]ll | [q]uit > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        if response in ("y", "yes"):
            return "yes"
        elif response in ("n", "no"):
            return "no"
        elif response in ("a", "all"):
            return "all"
        elif response in ("q", "quit"):
            return "quit"
        else:
            print("  Invalid input. Please enter y, n, a, or q.")


def prompt_initial_action(allow_investigate: bool = True) -> str | tuple[str, str | None]:
    """
    Prompt user for initial action after seeing full analysis.
    
    Returns:
        - 'accept_all', 'review', 'skip', 'quit' as strings
        - ('investigate_all', user_guidance) tuple when investigate is chosen
    """
    investigate_text = ' | [i]nvestigate all or i "guidance"' if allow_investigate else ""
    while True:
        try:
            response = input(f"\n[a]ccept all | [r]eview each{investigate_text} | [s]kip | [q]uit > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        response_lower = response.lower()
        
        if response_lower in ("a", "accept", "accept all"):
            return "accept_all"
        elif response_lower in ("r", "review", "review each"):
            return "review"
        elif response_lower in ("s", "skip"):
            return "skip"
        elif response_lower in ("q", "quit"):
            return "quit"
        elif allow_investigate:
            is_investigate, user_guidance = parse_investigate_command(response)
            if is_investigate:
                return ("investigate_all", user_guidance)
        
        valid = 'a, r, i or i "guidance", s, or q' if allow_investigate else "a, r, s, or q"
        print(f"  Invalid input. Please enter {valid}.")


def display_header(guideline_id: str, batch: int, current: int, total: int) -> None:
    """Display the header for a guideline review."""
    batch_name = BATCH_EXPECTED_PATTERNS.get(batch, {}).get("name", "Unknown")
    print()
    print("╔" + "═" * 78 + "╗")
    print(f"║  Outlier Review: {guideline_id:<40} ({current}/{total})".ljust(79) + "║")
    print(f"║  Batch: {batch} ({batch_name})".ljust(79) + "║")
    print("╚" + "═" * 78 + "╝")


def display_quick_reference(analysis: dict) -> None:
    """Display quick reference info for the guideline."""
    add6 = analysis.get("add6", {})
    comparison = analysis.get("comparison", {})
    flags = analysis.get("flags", {})
    active_flags = get_active_flags(flags)
    
    print(f"\nFlags: {', '.join(active_flags) if active_flags else 'None'}")
    print(f"\nQuick Reference:")
    print(f"  ADD-6: applicability_all_rust={add6.get('applicability_all_rust', 'N/A')}, "
          f"applicability_safe_rust={add6.get('applicability_safe_rust', 'N/A')}")
    
    # Show decision summary from comparison
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        app_changed = ctx_comp.get("applicability_changed", False)
        rat_changed = ctx_comp.get("rationale_type_changed", False)
        app_trans = ctx_comp.get("applicability_mapping_to_decision") or "no change"
        rat_trans = ctx_comp.get("rationale_type_mapping_to_decision") or "no change"
        print(f"  Decision ({ctx}): applicability {app_trans}, rationale {rat_trans}")


def interactive_review_guideline(
    guideline_id: str,
    root: Path,
    current: int,
    total: int,
    dry_run: bool = False,
) -> str:
    """
    Interactively review a single guideline.
    
    Flow:
    1. Display header and quick reference
    2. Display full LLM analysis (like --show)
    3. Prompt: [a]ccept all | [r]eview each | [s]kip | [q]uit
    4. If review: prompt per-aspect with [?] help option to re-show analysis
    
    Returns: 'continue', 'skip', or 'quit'
    """
    analysis = load_outlier_analysis(guideline_id, root)
    if not analysis:
        print(f"  WARNING: No analysis found for {guideline_id}, skipping")
        return "continue"
    
    batch = analysis.get("batch", 0)
    flags = analysis.get("flags", {})
    llm_analysis = analysis.get("llm_analysis", {})
    comparison = analysis.get("comparison", {})
    
    # Display header and quick reference
    display_header(guideline_id, batch, current, total)
    display_quick_reference(analysis)
    
    # Display full LLM analysis (Phase 1)
    display_llm_analysis(analysis)
    
    # Initialize human_review if needed
    if analysis.get("human_review") is None:
        analysis["human_review"] = create_human_review_section()
    
    human_review = analysis["human_review"]
    initialize_fls_structures(human_review, llm_analysis, comparison)
    
    # Check if already fully reviewed
    current_status = compute_overall_status(human_review, flags, llm_analysis)
    if current_status == "fully_reviewed":
        print(f"\n✓ Already fully reviewed")
        response = prompt_yes_no_skip_quit("Re-review this guideline?", show_help=False)
        if response == "quit":
            return "quit"
        elif response in ("no", "skip"):
            return "continue"
        # Otherwise continue to re-review
    
    # Initial action prompt (Phase 2)
    response = prompt_initial_action(allow_investigate=True)
    if response == "quit":
        return "quit"
    elif response == "accept_all":
        _accept_all(human_review, flags, llm_analysis)
        human_review["overall_status"] = "fully_reviewed"
        human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
        if not dry_run:
            save_outlier_analysis(guideline_id, analysis, root)
        print(f"\n✓ {guideline_id}: Accepted all LLM recommendations")
        _wait_for_enter()
        return "continue"
    
    # Check for investigate_all (with optional user guidance)
    is_inv, user_guidance = is_investigate_response(response)
    if is_inv:
        # Request investigation for all pending aspects
        output_investigation_request(guideline_id, "all", user_guidance=user_guidance)
        if wait_for_investigation_completion():
            # Reload analysis after investigation
            updated = load_outlier_analysis(guideline_id, root)
            if updated:
                analysis.update(updated)
                flags = analysis.get("flags", {})
                llm_analysis = analysis.get("llm_analysis", {})
                comparison = analysis.get("comparison", {})
                human_review = analysis.get("human_review", create_human_review_section())
                analysis["human_review"] = human_review
                initialize_fls_structures(human_review, llm_analysis, comparison)
            
            # Re-display with investigation findings
            print("\n" + "═" * 78)
            print("INVESTIGATION COMPLETE - Updated Analysis:")
            print("═" * 78)
            display_investigation_findings(analysis)
            display_llm_analysis(analysis)
            
            # Re-prompt for action
            response = prompt_initial_action(allow_investigate=False)  # Don't allow another investigate
            if response == "quit":
                return "quit"
            elif response == "accept_all":
                _accept_all(human_review, flags, llm_analysis)
                human_review["overall_status"] = "fully_reviewed"
                human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
                if not dry_run:
                    save_outlier_analysis(guideline_id, analysis, root)
                print(f"\n✓ {guideline_id}: Accepted all LLM recommendations")
                _wait_for_enter()
                return "continue"
            elif response == "skip":
                return "continue"
            # Otherwise continue to review each
        else:
            # Investigation cancelled, continue with review
            pass
    elif response == "skip":
        return "continue"
    
    # Detailed per-aspect review with help option
    # Pass analysis for re-display on '?'
    
    # 1. Categorization
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        result = _review_categorization(human_review, llm_analysis, comparison, flags, analysis, root)
        if result == "quit":
            return "quit"
        elif result == "accept_remaining":
            _accept_remaining(human_review, flags, llm_analysis, skip_categorization=True)
            human_review["overall_status"] = "fully_reviewed"
            human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
            if not dry_run:
                save_outlier_analysis(guideline_id, analysis, root)
            _display_review_summary(guideline_id, human_review, flags)
            _wait_for_enter()
            return "continue"
    
    # 2. FLS Removals
    if flags.get("fls_removed"):
        result = _review_fls_removals(human_review, llm_analysis, comparison, analysis, root)
        if result == "quit":
            return "quit"
        elif result == "accept_remaining":
            _accept_remaining(human_review, flags, llm_analysis, skip_fls_removals=True)
            human_review["overall_status"] = "fully_reviewed"
            human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
            if not dry_run:
                save_outlier_analysis(guideline_id, analysis, root)
            _display_review_summary(guideline_id, human_review, flags)
            _wait_for_enter()
            return "continue"
    
    # 3. FLS Additions
    if flags.get("fls_added"):
        result = _review_fls_additions(human_review, llm_analysis, comparison, analysis, root)
        if result == "quit":
            return "quit"
        elif result == "accept_remaining":
            _accept_remaining(human_review, flags, llm_analysis, skip_fls_additions=True)
            human_review["overall_status"] = "fully_reviewed"
            human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
            if not dry_run:
                save_outlier_analysis(guideline_id, analysis, root)
            _display_review_summary(guideline_id, human_review, flags)
            _wait_for_enter()
            return "continue"
    
    # 4. Specificity
    if flags.get("specificity_decreased"):
        result = _review_specificity(human_review, llm_analysis, analysis, root)
        if result == "quit":
            return "quit"
        elif result == "accept_remaining":
            _accept_remaining(human_review, flags, llm_analysis, skip_specificity=True)
            human_review["overall_status"] = "fully_reviewed"
            human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
            if not dry_run:
                save_outlier_analysis(guideline_id, analysis, root)
            _display_review_summary(guideline_id, human_review, flags)
            _wait_for_enter()
            return "continue"
    
    # 5. ADD-6 Divergence
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        result = _review_add6_divergence(human_review, llm_analysis, analysis.get("add6", {}), analysis, root)
        if result == "quit":
            return "quit"
        # No more aspects after this, so accept_remaining is the same as completing
    
    # Update status and save
    human_review["overall_status"] = compute_overall_status(human_review, flags, llm_analysis)
    human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
    
    if not dry_run:
        save_outlier_analysis(guideline_id, analysis, root)
    
    # Show summary
    _display_review_summary(guideline_id, human_review, flags)
    _wait_for_enter()
    
    return "continue"


def _accept_all(human_review: dict, flags: dict, llm_analysis: dict) -> None:
    """Accept all aspects based on LLM recommendations."""
    _accept_remaining(human_review, flags, llm_analysis)


def _accept_remaining(
    human_review: dict,
    flags: dict,
    llm_analysis: dict,
    skip_categorization: bool = False,
    skip_fls_removals: bool = False,
    skip_fls_additions: bool = False,
    skip_specificity: bool = False,
    skip_add6: bool = False,
) -> None:
    """Accept remaining aspects that haven't been decided yet."""
    # Categorization - now per-context
    if not skip_categorization and (flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier")):
        if not human_review.get("categorization"):
            human_review["categorization"] = {}
        for ctx in ["all_rust", "safe_rust"]:
            if not human_review["categorization"].get(ctx, {}).get("decision"):
                human_review["categorization"][ctx] = {
                    "decision": "accept",
                    "reason": "Accepted per LLM recommendation",
                }
    
    # FLS Removals
    if not skip_fls_removals:
        for fls_id, item in human_review.get("fls_removals", {}).items():
            for ctx in item.get("contexts", []):
                if "decisions" not in item:
                    item["decisions"] = {}
                if not item["decisions"].get(ctx):
                    item["decisions"][ctx] = {
                        "decision": "accept",
                        "reason": "Accepted per LLM recommendation",
                    }
    
    # FLS Additions
    if not skip_fls_additions:
        for fls_id, item in human_review.get("fls_additions", {}).items():
            for ctx in item.get("contexts", []):
                if "decisions" not in item:
                    item["decisions"] = {}
                if not item["decisions"].get(ctx):
                    item["decisions"][ctx] = {
                        "decision": "accept",
                        "reason": "Accepted per LLM recommendation",
                    }
    
    # Specificity
    if not skip_specificity and flags.get("specificity_decreased"):
        if not human_review.get("specificity"):
            human_review["specificity"] = {
                "decision": "accept",
                "reason": "Accepted per LLM recommendation",
            }
    
    # ADD-6 Divergence
    if not skip_add6 and (flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6")):
        if not human_review.get("add6_divergence"):
            human_review["add6_divergence"] = {
                "decision": "accept",
                "reason": "Accepted per LLM recommendation",
            }


def _review_categorization(human_review: dict, llm_analysis: dict, comparison: dict, flags: dict, analysis: dict, root: Path | None = None) -> str:
    """Review categorization changes per-context. Returns 'continue', 'quit', or 'accept_remaining'."""
    guideline_id = analysis.get("guideline_id", "Unknown")
    add6 = analysis.get("add6", {})
    context_metadata = analysis.get("context_metadata", {})
    
    print()
    print("═" * 78)
    print("CATEGORIZATION")
    print("═" * 78)
    
    # Display any existing investigation findings for categorization
    display_investigation_findings(analysis, aspect="categorization")
    
    # Get per-context LLM categorization (new format) or single verdict (old format)
    llm_cat = llm_analysis.get("categorization", {})
    
    # Check if it's the new per-context format or old single-verdict format
    is_per_context_format = llm_cat and (llm_cat.get("all_rust") is not None or llm_cat.get("safe_rust") is not None)
    
    if not is_per_context_format:
        # Old format - show single verdict as overview
        print(f"LLM Verdict (overall): {llm_cat.get('verdict', 'N/A')}")
        reasoning = llm_cat.get("reasoning")
        if reasoning:
            print(f"LLM Reasoning: {reasoning}")
    
    # Initialize per-context categorization if needed
    if human_review.get("categorization") is None or not isinstance(human_review.get("categorization"), dict):
        human_review["categorization"] = {}
    
    # Review each context separately
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        ctx_decision = context_metadata.get("decision", {}).get(ctx, {})
        ctx_mapping = context_metadata.get("mapping", {}).get(ctx, {})
        
        # Get actual values (from decision, falling back to mapping if unchanged)
        dec_app = ctx_decision.get("applicability") or ctx_mapping.get("applicability") or "N/A"
        dec_rat = ctx_decision.get("rationale_type") or ctx_mapping.get("rationale_type") or "N/A"
        dec_adj = ctx_decision.get("adjusted_category") or ctx_mapping.get("adjusted_category") or "N/A"
        
        # Get transition text for change indication
        app_changed = ctx_comp.get("applicability_changed", False)
        rat_changed = ctx_comp.get("rationale_type_changed", False)
        adj_changed = ctx_comp.get("adjusted_category_changed", False)
        
        app_trans = ctx_comp.get("applicability_mapping_to_decision") if app_changed else "no change from mapping"
        rat_trans = ctx_comp.get("rationale_type_mapping_to_decision") if rat_changed else "no change from mapping"
        adj_trans = ctx_comp.get("adjusted_category_mapping_to_decision") if adj_changed else "no change from mapping"
        
        # Get ADD-6 expected values
        add6_app_key = f"applicability_{ctx}"
        add6_app = add6.get(add6_app_key, "N/A")
        add6_adj = add6.get("adjusted_category", "N/A")
        
        # Check divergence
        app_diverges = ctx_comp.get("applicability_differs_from_add6", False)
        adj_diverges = ctx_comp.get("adjusted_category_differs_from_add6", False)
        
        print()
        print("─" * 78)
        print(f"Context: {ctx}")
        print("─" * 78)
        
        # Show per-context LLM verdict if available
        if is_per_context_format:
            ctx_llm = llm_cat.get(ctx, {})
            if ctx_llm:
                print(f"LLM Verdict: {ctx_llm.get('verdict', 'N/A')}")
                ctx_reasoning = ctx_llm.get("reasoning")
                if ctx_reasoning:
                    print(f"LLM Reasoning: {ctx_reasoning}")
                print()
        
        print(f"  Applicability:      {dec_app} ({app_trans})")
        print(f"  Rationale type:     {dec_rat} ({rat_trans})")
        print(f"  Adjusted category:  {dec_adj} ({adj_trans})")
        print()
        print(f"  ADD-6 Reference:")
        app_status = "✗ DIVERGES" if app_diverges else "✓ matches"
        adj_status = "✗ DIVERGES" if adj_diverges else "✓ matches"
        print(f"    Applicability:    {add6_app} {app_status}")
        print(f"    Adjusted category: {add6_adj} {adj_status}")
        
        # Check if already decided for this context
        existing = human_review["categorization"].get(ctx, {}).get("decision")
        if existing:
            print(f"\n  [Already decided: {existing}]")
            while True:
                response = prompt_yes_no_skip_quit(f"\nChange {ctx} categorization decision?", show_help=True, allow_investigate=True)
                if response == "help":
                    display_llm_analysis(analysis)
                    continue
                is_inv, user_guidance = is_investigate_response(response)
                if is_inv:
                    output_investigation_request(guideline_id, "categorization", context=ctx, user_guidance=user_guidance)
                    if wait_for_investigation_completion() and root:
                        updated = load_outlier_analysis(guideline_id, root)
                        if updated:
                            analysis.update(updated)
                            display_investigation_findings(analysis, aspect="categorization", context=ctx)
                    continue
                break
            if response == "quit":
                return "quit"
            elif response in ("no", "skip"):
                continue  # Keep existing decision, move to next context
        
        # Prompt for decision
        while True:
            response = prompt_yes_no_skip_quit(f"\nAccept {ctx} categorization?", show_help=True, allow_investigate=True)
            if response == "help":
                display_llm_analysis(analysis)
                continue
            is_inv, user_guidance = is_investigate_response(response)
            if is_inv:
                output_investigation_request(guideline_id, "categorization", context=ctx, user_guidance=user_guidance)
                if wait_for_investigation_completion() and root:
                    updated = load_outlier_analysis(guideline_id, root)
                    if updated:
                        analysis.update(updated)
                        display_investigation_findings(analysis, aspect="categorization", context=ctx)
                continue
            break
        
        if response == "quit":
            return "quit"
        elif response == "skip":
            pass  # Leave as-is for this context
        elif response == "yes":
            human_review["categorization"][ctx] = {"decision": "accept", "reason": None}
        elif response == "no":
            human_review["categorization"][ctx] = {"decision": "reject", "reason": None}
    
    return "continue"


def _review_fls_removals(human_review: dict, llm_analysis: dict, comparison: dict, analysis: dict, root: Path | None = None) -> str:
    """Review FLS removals. Returns 'continue', 'quit', or 'accept_remaining'."""
    removals = llm_analysis.get("fls_removals", {})
    per_id = removals.get("per_id", {})
    guideline_id = analysis.get("guideline_id", "Unknown")
    
    if not human_review.get("fls_removals"):
        return "continue"
    
    removal_count = sum(len(item.get("contexts", [])) for item in human_review["fls_removals"].values())
    if removal_count == 0:
        return "continue"
    
    print()
    print("═" * 78)
    print(f"FLS REMOVALS ({removal_count} items)")
    print("═" * 78)
    print(f"LLM Verdict: {removals.get('verdict', 'N/A')}")
    
    # Show overall LLM reasoning for removals
    overall_reasoning = removals.get("reasoning")
    if overall_reasoning:
        print(f"LLM Reasoning: {overall_reasoning}")
    
    idx = 0
    total_items = removal_count
    for fls_id, item in human_review["fls_removals"].items():
        contexts = item.get("contexts", [])
        llm_info = per_id.get(fls_id, {})
        
        for ctx in contexts:
            idx += 1
            print(f"\n  [{idx}/{total_items}] {fls_id}: {item.get('title', 'Unknown')} (category: {item.get('category')})")
            print(f"        Contexts: {', '.join(contexts)}")
            
            # Display any existing investigation findings for this FLS ID
            display_investigation_findings(analysis, aspect="fls_removal", fls_id=fls_id, context=ctx)
            
            # Show the original reason why this FLS was matched (from mapping)
            # No truncation - reviewer needs full context to make informed decisions
            original_reason = llm_info.get("original_reason")
            if original_reason:
                print(f"        Original reason: {original_reason}")
            
            # Get LLM justification for this context
            removal_decisions = llm_info.get("removal_decisions", {})
            justification = removal_decisions.get(ctx, "No justification provided")
            print(f"        LLM justification ({ctx}): {justification}")
            
            # Check if already decided
            existing = item.get("decisions", {}).get(ctx, {}).get("decision")
            if existing:
                print(f"        [Already decided: {existing}]")
                while True:
                    response = prompt_yes_no_skip_quit(f"        Change decision for {ctx}?", show_help=True, allow_investigate=True)
                    if response == "help":
                        display_llm_analysis(analysis)
                        continue
                    is_inv, user_guidance = is_investigate_response(response)
                    if is_inv:
                        output_investigation_request(guideline_id, "fls_removal", fls_id=fls_id, context=ctx, user_guidance=user_guidance)
                        if wait_for_investigation_completion() and root:
                            # Reload analysis after investigation
                            updated = load_outlier_analysis(guideline_id, root)
                            if updated:
                                analysis.update(updated)
                                display_investigation_findings(analysis, aspect="fls_removal", fls_id=fls_id, context=ctx)
                        continue
                    break
                if response == "quit":
                    return "quit"
                elif response in ("no", "skip"):
                    continue
            
            while True:
                response = prompt_yes_no_na(f"        Accept removal for {ctx}?", allow_na=False, show_help=True, allow_investigate=True)
                if response == "help":
                    display_llm_analysis(analysis)
                    continue
                is_inv, user_guidance = is_investigate_response(response)
                if is_inv:
                    output_investigation_request(guideline_id, "fls_removal", fls_id=fls_id, context=ctx, user_guidance=user_guidance)
                    if wait_for_investigation_completion() and root:
                        # Reload analysis after investigation
                        updated = load_outlier_analysis(guideline_id, root)
                        if updated:
                            analysis.update(updated)
                            display_investigation_findings(analysis, aspect="fls_removal", fls_id=fls_id, context=ctx)
                    continue
                break
            
            if response == "quit":
                return "quit"
            else:
                if "decisions" not in item:
                    item["decisions"] = {}
                item["decisions"][ctx] = {
                    "decision": "accept" if response == "yes" else "reject",
                    "reason": None,
                }
    
    return "continue"


def _review_fls_additions(human_review: dict, llm_analysis: dict, comparison: dict, analysis: dict, root: Path | None = None) -> str:
    """Review FLS additions. Returns 'continue', 'quit', or 'accept_remaining'."""
    additions = llm_analysis.get("fls_additions", {})
    per_id = additions.get("per_id", {})
    guideline_id = analysis.get("guideline_id", "Unknown")
    
    if not human_review.get("fls_additions"):
        return "continue"
    
    addition_count = sum(len(item.get("contexts", [])) for item in human_review["fls_additions"].values())
    if addition_count == 0:
        return "continue"
    
    print()
    print("═" * 78)
    print(f"FLS ADDITIONS ({addition_count} items)")
    print("═" * 78)
    print(f"LLM Verdict: {additions.get('verdict', 'N/A')}")
    
    # Show overall LLM reasoning for additions
    overall_reasoning = additions.get("reasoning")
    if overall_reasoning:
        print(f"LLM Reasoning: {overall_reasoning}")
    
    idx = 0
    total_items = addition_count
    for fls_id, item in human_review["fls_additions"].items():
        contexts = item.get("contexts", [])
        llm_info = per_id.get(fls_id, {})
        
        for ctx in contexts:
            idx += 1
            print(f"\n  [{idx}/{total_items}] {fls_id}: {item.get('title', 'Unknown')} (category: {item.get('category')})")
            print(f"        Contexts: {', '.join(contexts)}")
            
            # Display any existing investigation findings for this FLS ID
            display_investigation_findings(analysis, aspect="fls_addition", fls_id=fls_id, context=ctx)
            
            # Show the new reason why this FLS was added (from decision)
            # No truncation - reviewer needs full context to make informed decisions
            new_reason = llm_info.get("new_reason")
            if new_reason:
                print(f"        New reason: {new_reason}")
            
            # Get LLM justification
            addition_decisions = llm_info.get("addition_decisions", {})
            justification = addition_decisions.get(ctx, "No justification provided")
            print(f"        LLM justification ({ctx}): {justification}")
            
            # Check if already decided
            existing = item.get("decisions", {}).get(ctx, {}).get("decision")
            if existing:
                print(f"        [Already decided: {existing}]")
                while True:
                    response = prompt_yes_no_skip_quit(f"        Change decision for {ctx}?", show_help=True, allow_investigate=True)
                    if response == "help":
                        display_llm_analysis(analysis)
                        continue
                    is_inv, user_guidance = is_investigate_response(response)
                    if is_inv:
                        output_investigation_request(guideline_id, "fls_addition", fls_id=fls_id, context=ctx, user_guidance=user_guidance)
                        if wait_for_investigation_completion() and root:
                            updated = load_outlier_analysis(guideline_id, root)
                            if updated:
                                analysis.update(updated)
                                display_investigation_findings(analysis, aspect="fls_addition", fls_id=fls_id, context=ctx)
                        continue
                    break
                if response == "quit":
                    return "quit"
                elif response in ("no", "skip"):
                    continue
            
            while True:
                response = prompt_yes_no_na(f"        Accept addition for {ctx}?", allow_na=False, show_help=True, allow_investigate=True)
                if response == "help":
                    display_llm_analysis(analysis)
                    continue
                is_inv, user_guidance = is_investigate_response(response)
                if is_inv:
                    output_investigation_request(guideline_id, "fls_addition", fls_id=fls_id, context=ctx, user_guidance=user_guidance)
                    if wait_for_investigation_completion() and root:
                        updated = load_outlier_analysis(guideline_id, root)
                        if updated:
                            analysis.update(updated)
                            display_investigation_findings(analysis, aspect="fls_addition", fls_id=fls_id, context=ctx)
                    continue
                break
            
            if response == "quit":
                return "quit"
            else:
                if "decisions" not in item:
                    item["decisions"] = {}
                item["decisions"][ctx] = {
                    "decision": "accept" if response == "yes" else "reject",
                    "reason": None,
                }
    
    return "continue"


def _review_specificity(human_review: dict, llm_analysis: dict, analysis: dict, root: Path | None = None) -> str:
    """Review specificity loss. Returns 'continue', 'quit', or 'accept_remaining'."""
    guideline_id = analysis.get("guideline_id", "Unknown")
    spec = llm_analysis.get("specificity", {})
    
    print()
    print("═" * 78)
    print("SPECIFICITY")
    print("═" * 78)
    
    # Display any existing investigation findings for specificity
    display_investigation_findings(analysis, aspect="specificity")
    
    print(f"LLM Verdict: {spec.get('verdict', 'N/A')}")
    
    # Show full LLM reasoning - no truncation
    reasoning = spec.get("reasoning")
    if reasoning:
        print(f"LLM Reasoning: {reasoning}")
    
    # Show all lost paragraphs - no limit, reviewer needs complete picture
    lost = spec.get("lost_paragraphs", [])
    if lost:
        print(f"\nLost paragraphs ({len(lost)}):")
        for p in lost:
            print(f"  - {p.get('fls_id')} (category {p.get('category')}): {p.get('fls_title')}")
    
    while True:
        response = prompt_yes_no_skip_quit("\nAccept specificity loss?", show_help=True, allow_investigate=True)
        if response == "help":
            display_llm_analysis(analysis)
            continue
        is_inv, user_guidance = is_investigate_response(response)
        if is_inv:
            output_investigation_request(guideline_id, "specificity", user_guidance=user_guidance)
            if wait_for_investigation_completion() and root:
                updated = load_outlier_analysis(guideline_id, root)
                if updated:
                    analysis.update(updated)
                    display_investigation_findings(analysis, aspect="specificity")
            continue
        break
    
    if response == "quit":
        return "quit"
    elif response == "skip":
        pass
    elif response == "yes":
        human_review["specificity"] = {"decision": "accept", "reason": None}
    elif response == "no":
        human_review["specificity"] = {"decision": "reject", "reason": None}
    
    return "continue"


def _review_add6_divergence(human_review: dict, llm_analysis: dict, add6: dict, analysis: dict, root: Path | None = None) -> str:
    """Review ADD-6 divergence. Returns 'continue', 'quit', or 'accept_remaining'."""
    guideline_id = analysis.get("guideline_id", "Unknown")
    div = llm_analysis.get("add6_divergence", {})
    comparison = analysis.get("comparison", {})
    
    print()
    print("═" * 78)
    print("ADD-6 DIVERGENCE")
    print("═" * 78)
    
    # Display any existing investigation findings for ADD-6
    display_investigation_findings(analysis, aspect="add6_divergence")
    
    print(f"LLM Verdict: {div.get('verdict', 'N/A')}")
    
    # Show full LLM reasoning - no truncation
    reasoning = div.get("reasoning")
    if reasoning:
        print(f"LLM Reasoning: {reasoning}")
    
    print(f"\nADD-6 Reference:")
    print(f"  applicability_all_rust: {add6.get('applicability_all_rust', 'N/A')}")
    print(f"  applicability_safe_rust: {add6.get('applicability_safe_rust', 'N/A')}")
    print(f"  adjusted_category: {add6.get('adjusted_category', 'N/A')}")
    
    # Show per-context divergence status
    print(f"\nPer-context divergence:")
    for ctx in ["all_rust", "safe_rust"]:
        add6_key = f"applicability_{ctx}"
        add6_app = add6.get(add6_key, "N/A")
        
        ctx_comp = comparison.get(ctx, {})
        # Get decision applicability from comparison data
        dec_app = "N/A"
        if ctx_comp:
            if not ctx_comp.get("applicability_changed", True):
                dec_app = "(unchanged)"
            else:
                trans = ctx_comp.get("applicability_mapping_to_decision")
                if trans:
                    dec_app = trans.split("→")[-1] if "→" in trans else trans
        
        diverges = ctx_comp.get("applicability_differs_from_add6", False)
        status = "✗ DIVERGES" if diverges else "✓"
        print(f"  {ctx}: ADD-6={add6_app}, Decision={dec_app} {status}")
    
    while True:
        response = prompt_yes_no_skip_quit("\nAccept divergence from ADD-6?", show_help=True, allow_investigate=True)
        if response == "help":
            display_llm_analysis(analysis)
            continue
        is_inv, user_guidance = is_investigate_response(response)
        if is_inv:
            output_investigation_request(guideline_id, "add6_divergence", user_guidance=user_guidance)
            if wait_for_investigation_completion() and root:
                updated = load_outlier_analysis(guideline_id, root)
                if updated:
                    analysis.update(updated)
                    display_investigation_findings(analysis, aspect="add6_divergence")
            continue
        break
    
    if response == "quit":
        return "quit"
    elif response == "skip":
        pass
    elif response == "yes":
        human_review["add6_divergence"] = {"decision": "accept", "reason": None}
    elif response == "no":
        human_review["add6_divergence"] = {"decision": "reject", "reason": None}
    
    return "continue"


def _display_review_summary(guideline_id: str, human_review: dict, flags: dict) -> None:
    """Display summary of review decisions."""
    print()
    print("═" * 78)
    print(f"✓ {guideline_id} review complete")
    print(f"  Overall status: {human_review.get('overall_status')}")
    
    cat = human_review.get("categorization", {})
    if cat:
        cat_decisions = []
        for ctx in ["all_rust", "safe_rust"]:
            dec = cat.get(ctx, {}).get("decision")
            if dec:
                cat_decisions.append(f"{ctx}={dec}")
        if cat_decisions:
            print(f"  Categorization: {', '.join(cat_decisions)}")
    
    removal_decisions = []
    for fls_id, item in human_review.get("fls_removals", {}).items():
        for ctx, dec in item.get("decisions", {}).items():
            removal_decisions.append(f"{fls_id}:{ctx}={dec.get('decision')}")
    if removal_decisions:
        print(f"  FLS Removals: {', '.join(removal_decisions[:5])}" + 
              (f" (+{len(removal_decisions)-5} more)" if len(removal_decisions) > 5 else ""))
    
    addition_decisions = []
    for fls_id, item in human_review.get("fls_additions", {}).items():
        for ctx, dec in item.get("decisions", {}).items():
            addition_decisions.append(f"{fls_id}:{ctx}={dec.get('decision')}")
    if addition_decisions:
        print(f"  FLS Additions: {', '.join(addition_decisions[:5])}" + 
              (f" (+{len(addition_decisions)-5} more)" if len(addition_decisions) > 5 else ""))
    
    if human_review.get("specificity"):
        print(f"  Specificity: {human_review['specificity'].get('decision')}")
    
    if human_review.get("add6_divergence"):
        print(f"  ADD-6 Divergence: {human_review['add6_divergence'].get('decision')}")


def _wait_for_enter() -> None:
    """Wait for user to press Enter to continue."""
    try:
        input("\nPress Enter to continue to next outlier...")
    except (EOFError, KeyboardInterrupt):
        pass


def run_interactive_mode(
    root: Path,
    batch: int | None,
    start_from: str | None,
    pending_only: bool,
    dry_run: bool,
) -> None:
    """Run interactive review mode for a batch or all guidelines."""
    # Get guidelines to review
    if batch is not None:
        guidelines = get_guidelines_for_batch(batch, root)
        scope = f"batch {batch}"
    else:
        all_pairs = get_all_guidelines(root)
        guidelines = [g for _, g in all_pairs]
        scope = "all batches"
    
    if pending_only:
        pending = get_pending_guidelines(root, batch)
        guidelines = [g for g in guidelines if g in pending]
        scope = f"{scope} (pending only)"
    
    if not guidelines:
        print(f"No guidelines to review for {scope}")
        return
    
    # Find start index
    start_idx = 0
    if start_from:
        try:
            start_idx = guidelines.index(start_from)
        except ValueError:
            print(f"WARNING: Guideline '{start_from}' not found in {scope}, starting from beginning")
    
    total = len(guidelines)
    reviewed_count = 0
    
    print(f"\n{'='*60}")
    print(f"Interactive Review: {scope}")
    print(f"{'='*60}")
    print(f"Guidelines: {total}")
    if start_idx > 0:
        print(f"Starting from: {guidelines[start_idx]} ({start_idx + 1}/{total})")
    if dry_run:
        print("DRY RUN: Changes will not be saved")
    print()
    
    for i, guideline_id in enumerate(guidelines[start_idx:], start=start_idx + 1):
        result = interactive_review_guideline(guideline_id, root, i, total, dry_run)
        
        if result == "quit":
            print(f"\nExiting. Reviewed {reviewed_count} guidelines.")
            print(f"Resume with: --start-from \"{guideline_id}\"")
            break
        elif result == "continue":
            reviewed_count += 1
    else:
        print(f"\n{'='*60}")
        print(f"Review complete! Reviewed {reviewed_count} guidelines.")
        print(f"{'='*60}")
    
    # Update review state summary
    if not dry_run:
        review_state = load_review_state(root)
        review_state["summary"] = recompute_review_summary(root)
        save_review_state(review_state, root)


def main():
    parser = argparse.ArgumentParser(
        description="Interactive human review for outlier analysis."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    
    # Scope selection
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--guideline",
        help="Review a single guideline (e.g., 'Rule 10.1')",
    )
    scope_group.add_argument(
        "--batch",
        type=int,
        help="Review all guidelines in a specific batch",
    )
    scope_group.add_argument(
        "--all",
        action="store_true",
        help="Review all guidelines across all batches",
    )
    
    # Interactive mode options
    parser.add_argument(
        "--start-from",
        metavar="GUIDELINE",
        help="Start/resume from a specific guideline (for --batch or --all)",
    )
    parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Only review guidelines that aren't fully reviewed yet",
    )
    
    # Display modes
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display LLM analysis without making decisions (single guideline only)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode with prompts (default for --batch/--all)",
    )
    
    # Context for FLS operations
    parser.add_argument(
        "--context",
        choices=VALID_CONTEXTS,
        help="Context for FLS accept/reject operations (all_rust, safe_rust, both)",
    )
    
    # Accept/reject actions (single guideline mode)
    parser.add_argument(
        "--accept-all",
        action="store_true",
        help="Accept all aspects of the outlier decision",
    )
    parser.add_argument(
        "--accept-categorization",
        action="store_true",
        help="Accept categorization changes",
    )
    parser.add_argument(
        "--reject-categorization",
        action="store_true",
        help="Reject categorization changes",
    )
    parser.add_argument(
        "--accept-removal",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Accept a specific FLS removal (requires --context)",
    )
    parser.add_argument(
        "--reject-removal",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Reject a specific FLS removal (requires --context)",
    )
    parser.add_argument(
        "--accept-addition",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Accept a specific FLS addition (requires --context)",
    )
    parser.add_argument(
        "--reject-addition",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Reject a specific FLS addition (requires --context)",
    )
    parser.add_argument(
        "--accept-add6-divergence",
        action="store_true",
        help="Accept divergence from ADD-6",
    )
    parser.add_argument(
        "--reject-add6-divergence",
        action="store_true",
        help="Reject divergence from ADD-6",
    )
    parser.add_argument(
        "--accept-specificity",
        action="store_true",
        help="Accept loss of specificity",
    )
    parser.add_argument(
        "--reject-specificity",
        action="store_true",
        help="Reject loss of specificity",
    )
    
    # Bulk operations
    parser.add_argument(
        "--bulk-accept-removal",
        metavar="FLS_ID",
        help="Accept this FLS removal across ALL outliers (requires --context)",
    )
    parser.add_argument(
        "--bulk-accept-addition",
        metavar="FLS_ID",
        help="Accept this FLS addition across ALL outliers (requires --context)",
    )
    
    # Common options
    parser.add_argument(
        "--reason",
        help="Reason for the decision",
    )
    parser.add_argument(
        "--notes",
        help="Additional notes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without saving",
    )
    
    args = parser.parse_args()
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    # Validate context requirement for FLS operations
    fls_operations = (
        args.accept_removal or args.reject_removal or
        args.accept_addition or args.reject_addition or
        args.bulk_accept_removal or args.bulk_accept_addition
    )
    if fls_operations and not args.context:
        print("ERROR: --context is required for FLS accept/reject operations", file=sys.stderr)
        print("  Valid contexts: all_rust, safe_rust, both", file=sys.stderr)
        sys.exit(1)
    
    # Handle bulk operations
    if args.bulk_accept_removal or args.bulk_accept_addition:
        review_state = load_review_state(root)
        
        if args.bulk_accept_removal:
            fls_id = args.bulk_accept_removal
            ctx = args.context
            bulk_rules = review_state.setdefault("bulk_rules", {})
            bulk_removals = bulk_rules.setdefault("accept_removals", {})
            
            if fls_id not in bulk_removals:
                bulk_removals[fls_id] = {"contexts": [], "reason": None}
            
            if ctx == "both":
                for c in ["all_rust", "safe_rust"]:
                    if c not in bulk_removals[fls_id]["contexts"]:
                        bulk_removals[fls_id]["contexts"].append(c)
            elif ctx not in bulk_removals[fls_id]["contexts"]:
                bulk_removals[fls_id]["contexts"].append(ctx)
            
            if args.reason:
                bulk_removals[fls_id]["reason"] = args.reason
            
            print(f"Added bulk rule: accept removal of {fls_id} for context(s): {', '.join(bulk_removals[fls_id]['contexts'])}")
        
        if args.bulk_accept_addition:
            fls_id = args.bulk_accept_addition
            ctx = args.context
            bulk_rules = review_state.setdefault("bulk_rules", {})
            bulk_additions = bulk_rules.setdefault("accept_additions", {})
            
            if fls_id not in bulk_additions:
                bulk_additions[fls_id] = {"contexts": [], "reason": None}
            
            if ctx == "both":
                for c in ["all_rust", "safe_rust"]:
                    if c not in bulk_additions[fls_id]["contexts"]:
                        bulk_additions[fls_id]["contexts"].append(c)
            elif ctx not in bulk_additions[fls_id]["contexts"]:
                bulk_additions[fls_id]["contexts"].append(ctx)
            
            if args.reason:
                bulk_additions[fls_id]["reason"] = args.reason
            
            print(f"Added bulk rule: accept addition of {fls_id} for context(s): {', '.join(bulk_additions[fls_id]['contexts'])}")
        
        if not args.dry_run:
            save_review_state(review_state, root)
            print("Saved bulk rules to review_state.json")
        else:
            print("[DRY RUN] Would save bulk rules")
        
        return
    
    # Interactive batch mode
    if args.batch is not None or args.all:
        batch = args.batch if args.batch is not None else None
        run_interactive_mode(
            root=root,
            batch=batch,
            start_from=args.start_from,
            pending_only=args.pending_only,
            dry_run=args.dry_run,
        )
        return
    
    # Single guideline operations
    if not args.guideline:
        print("ERROR: --guideline, --batch, or --all is required", file=sys.stderr)
        print("\nUsage examples:", file=sys.stderr)
        print("  Interactive batch mode:  uv run review-outliers --standard misra-c --batch 1", file=sys.stderr)
        print("  Single guideline show:   uv run review-outliers --standard misra-c --guideline \"Rule 10.1\" --show", file=sys.stderr)
        print("  Accept all for one:      uv run review-outliers --standard misra-c --guideline \"Rule 10.1\" --accept-all", file=sys.stderr)
        sys.exit(1)
    
    # Load outlier analysis
    analysis = load_outlier_analysis(args.guideline, root)
    if not analysis:
        print(f"ERROR: No outlier analysis found for {args.guideline}", file=sys.stderr)
        sys.exit(1)
    
    # Show mode - display and exit
    if args.show:
        display_llm_analysis(analysis)
        display_pending_decisions(analysis)
        return
    
    # Interactive mode for single guideline
    if args.interactive:
        result = interactive_review_guideline(args.guideline, root, 1, 1, args.dry_run)
        return
    
    # CLI-flag mode for single guideline
    if analysis.get("human_review") is None:
        analysis["human_review"] = create_human_review_section()
    
    human_review = analysis["human_review"]
    flags = analysis.get("flags", {})
    comparison = analysis.get("comparison", {})
    llm_analysis = analysis.get("llm_analysis", {})
    
    initialize_fls_structures(human_review, llm_analysis, comparison)
    
    changes_made = False
    
    # Process accept-all
    if args.accept_all:
        _accept_all(human_review, flags, llm_analysis)
        changes_made = True
        print(f"Accepted all aspects for {args.guideline}")
    
    # Process categorization
    if args.accept_categorization:
        human_review["categorization"] = {"decision": "accept", "reason": args.reason}
        changes_made = True
        print(f"Accepted categorization for {args.guideline}")
    
    if args.reject_categorization:
        human_review["categorization"] = {"decision": "reject", "reason": args.reason}
        changes_made = True
        print(f"Rejected categorization for {args.guideline}")
    
    # Process FLS removals
    for fls_id in args.accept_removal:
        if apply_fls_decision(human_review, human_review["fls_removals"], fls_id, args.context, "accept", args.reason):
            changes_made = True
            print(f"Accepted removal of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in removals list for context {args.context}")
    
    for fls_id in args.reject_removal:
        if apply_fls_decision(human_review, human_review["fls_removals"], fls_id, args.context, "reject", args.reason):
            changes_made = True
            print(f"Rejected removal of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in removals list for context {args.context}")
    
    # Process FLS additions
    for fls_id in args.accept_addition:
        if apply_fls_decision(human_review, human_review["fls_additions"], fls_id, args.context, "accept", args.reason):
            changes_made = True
            print(f"Accepted addition of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in additions list for context {args.context}")
    
    for fls_id in args.reject_addition:
        if apply_fls_decision(human_review, human_review["fls_additions"], fls_id, args.context, "reject", args.reason):
            changes_made = True
            print(f"Rejected addition of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in additions list for context {args.context}")
    
    # Process ADD-6 divergence
    if args.accept_add6_divergence:
        human_review["add6_divergence"] = {"decision": "accept", "reason": args.reason}
        changes_made = True
        print(f"Accepted ADD-6 divergence for {args.guideline}")
    
    if args.reject_add6_divergence:
        human_review["add6_divergence"] = {"decision": "reject", "reason": args.reason}
        changes_made = True
        print(f"Rejected ADD-6 divergence for {args.guideline}")
    
    # Process specificity
    if args.accept_specificity:
        human_review["specificity"] = {"decision": "accept", "reason": args.reason}
        changes_made = True
        print(f"Accepted specificity loss for {args.guideline}")
    
    if args.reject_specificity:
        human_review["specificity"] = {"decision": "reject", "reason": args.reason}
        changes_made = True
        print(f"Rejected specificity loss for {args.guideline}")
    
    # Add notes
    if args.notes:
        human_review["notes"] = args.notes
        changes_made = True
    
    if not changes_made:
        print("No changes specified. Use --show to view analysis, or --accept-all, etc.")
        print("\nFor FLS operations, --context is required. Example:")
        print("  --accept-removal fls_xyz123 --context all_rust")
        sys.exit(1)
    
    # Update status
    human_review["overall_status"] = compute_overall_status(human_review, flags, llm_analysis)
    human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
    analysis["human_review"] = human_review
    
    if args.dry_run:
        import json
        print("\n[DRY RUN] Would update human_review:")
        print(json.dumps(human_review, indent=2))
        return
    
    save_outlier_analysis(args.guideline, analysis, root)
    print(f"\nSaved review to outlier analysis file")
    print(f"Overall status: {human_review['overall_status']}")
    
    review_state = load_review_state(root)
    review_state["summary"] = recompute_review_summary(root)
    save_review_state(review_state, root)


if __name__ == "__main__":
    main()
