#!/usr/bin/env python3
"""
record-outlier-analysis - Record LLM analysis for flagged guidelines.

This tool records LLM analysis with full context for flagged guidelines,
including the full comparison data, rich FLS content, and per-aspect verdicts.

The tool enforces per-context acknowledgment of all flagged changes and divergences
to prevent lazy analysis that skips over important items.

Usage:
    uv run record-outlier-analysis --standard misra-c --guideline "Dir 4.3" --batch 1 \\
        --analysis-summary "MISRA Dir 4.3 requires assembly encapsulation..." \\
        --categorization-verdict-all-rust appropriate \\
        --categorization-reasoning-all-rust "applicability=yes correct - asm! encapsulates" \\
        --categorization-verdict-safe-rust appropriate \\
        --categorization-reasoning-safe-rust "applicability=no correct - requires unsafe" \\
        --cat-ack-diverge-applicability-safe-rust "ADD-6 says Yes but asm! requires unsafe per FLS fls_s5nfhBFOk8Bu" \\
        --fls-removals-verdict inappropriate \\
        --fls-removals-reasoning "Removed paragraphs are directly relevant legality rules" \\
        --fls-removal-detail "fls_3fg60jblx0xb:all_rust:KEEP - directly relevant legality rule" \\
        --add6-divergence-verdict justified \\
        --add6-divergence-reasoning "safe_rust cannot use asm!, divergence is correct" \\
        --overall-recommendation accept
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_outlier_analysis_dir,
    load_comparison_data,
    load_outlier_analysis,
    save_outlier_analysis,
    guideline_to_filename,
    enrich_match_with_fls_content,
    get_active_flags,
    save_json_file,
)


# Minimum lengths for validation
MIN_ACK_LENGTH = 20  # For acknowledgment fields
MIN_FLS_DETAIL_LENGTH = 50  # For per-FLS-ID justifications (must quote FLS)


def parse_fls_detail(detail_str: str) -> tuple[str, str, str]:
    """Parse 'fls_id:context:justification' format.
    
    Returns:
        Tuple of (fls_id, context, justification)
        Context is one of: 'all_rust', 'safe_rust', 'both'
    """
    parts = detail_str.split(":", 2)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid detail format: {detail_str}. "
            f"Expected 'fls_id:context:justification' where context is all_rust|safe_rust|both"
        )
    fls_id = parts[0].strip()
    context = parts[1].strip().lower()
    justification = parts[2].strip()
    
    valid_contexts = {"all_rust", "safe_rust", "both"}
    if context not in valid_contexts:
        raise ValueError(
            f"Invalid context '{context}' in {detail_str}. "
            f"Must be one of: {', '.join(sorted(valid_contexts))}"
        )
    
    return fls_id, context, justification


def validate_fls_detail_justification(fls_id: str, justification: str, detail_type: str) -> list[str]:
    """
    Validate FLS detail justification meets quality requirements.
    
    Requirements:
    - Minimum 50 characters
    - Must reference FLS content (contains 'FLS', quotes, or fls_id patterns)
    
    Args:
        fls_id: The FLS ID being justified
        justification: The justification text
        detail_type: 'removal' or 'addition' for error messages
    
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check minimum length
    if len(justification) < MIN_FLS_DETAIL_LENGTH:
        errors.append(
            f"--fls-{detail_type}-detail for {fls_id}: justification too short "
            f"(min {MIN_FLS_DETAIL_LENGTH} chars, got {len(justification)}). "
            f"Must include FLS quote or specific reference."
        )
    
    # Check for FLS reference indicators
    has_fls_reference = (
        "FLS" in justification or
        "fls_" in justification.lower() or
        '"' in justification or
        "'" in justification or
        "Per FLS" in justification or
        "states" in justification.lower()
    )
    
    if not has_fls_reference:
        errors.append(
            f"--fls-{detail_type}-detail for {fls_id}: justification must reference FLS content. "
            f"Include a quote (using quotes), 'FLS', 'fls_id', or 'Per FLS: ...' pattern."
        )
    
    return errors


def get_diverging_contexts(comparison: dict, add6: dict) -> list[str]:
    """
    Return list of contexts that diverge from ADD-6.
    
    Checks both applicability and adjusted_category divergence per context.
    """
    diverging = []
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        if ctx_comp.get("applicability_differs_from_add6"):
            add6_key = f"applicability_{ctx}"
            add6_val = add6.get(add6_key, "N/A")
            diverging.append(f"{ctx} (applicability differs from ADD-6={add6_val})")
        if ctx_comp.get("adjusted_category_differs_from_add6"):
            add6_val = add6.get("adjusted_category", "N/A")
            diverging.append(f"{ctx} (adjusted_category differs from ADD-6={add6_val})")
    return diverging


def build_categorization_per_context(
    ctx: str,
    comparison_data: dict,
    verdict: str | None,
    reasoning: str | None,
    ack_change_applicability: str | None,
    ack_change_rationale: str | None,
    ack_change_category: str | None,
    ack_diverge_applicability: str | None,
    ack_diverge_category: str | None,
) -> dict:
    """
    Build the per-context categorization structure with actual values and acknowledgments.
    
    Returns a dict with:
    - actual_values: current decision values
    - changes_from_mapping: detected changes (with from/to values) or null
    - diverges_from_add6: detected divergences (with decision/add6 values) or null
    - verdict: LLM verdict
    - reasoning: LLM reasoning
    - change_acknowledgments: explicit acknowledgments of changes
    - divergence_acknowledgments: explicit acknowledgments of divergences
    """
    comparison = comparison_data.get("comparison", {}).get(ctx, {})
    decision = comparison_data.get("decision", {}).get(ctx, {})
    mapping = comparison_data.get("mapping", {}).get(ctx, {})
    add6 = comparison_data.get("add6", {})
    
    # Build actual values from decision
    actual_values = {
        "applicability": decision.get("applicability"),
        "rationale_type": decision.get("rationale_type"),
        "adjusted_category": decision.get("adjusted_category"),
    }
    
    # Build changes_from_mapping (only for fields that changed)
    changes_from_mapping = {}
    if comparison.get("applicability_changed"):
        changes_from_mapping["applicability"] = {
            "from": mapping.get("applicability"),
            "to": decision.get("applicability"),
        }
    if comparison.get("rationale_type_changed"):
        changes_from_mapping["rationale_type"] = {
            "from": mapping.get("rationale_type"),
            "to": decision.get("rationale_type"),
        }
    if comparison.get("adjusted_category_changed"):
        changes_from_mapping["adjusted_category"] = {
            "from": mapping.get("adjusted_category"),
            "to": decision.get("adjusted_category"),
        }
    
    # Build diverges_from_add6 (only for fields that diverge)
    diverges_from_add6 = {}
    add6_app_key = f"applicability_{ctx}"
    if comparison.get("applicability_differs_from_add6"):
        diverges_from_add6["applicability"] = {
            "decision": decision.get("applicability"),
            "add6": add6.get(add6_app_key),
        }
    if comparison.get("adjusted_category_differs_from_add6"):
        diverges_from_add6["adjusted_category"] = {
            "decision": decision.get("adjusted_category"),
            "add6": add6.get("adjusted_category"),
        }
    
    # Build acknowledgments (only include those provided)
    change_acknowledgments = {}
    if ack_change_applicability:
        change_acknowledgments["applicability"] = ack_change_applicability
    if ack_change_rationale:
        change_acknowledgments["rationale_type"] = ack_change_rationale
    if ack_change_category:
        change_acknowledgments["adjusted_category"] = ack_change_category
    
    divergence_acknowledgments = {}
    if ack_diverge_applicability:
        divergence_acknowledgments["applicability"] = ack_diverge_applicability
    if ack_diverge_category:
        divergence_acknowledgments["adjusted_category"] = ack_diverge_category
    
    return {
        "actual_values": actual_values,
        "changes_from_mapping": changes_from_mapping if changes_from_mapping else None,
        "diverges_from_add6": diverges_from_add6 if diverges_from_add6 else None,
        "verdict": verdict,
        "reasoning": reasoning,
        "change_acknowledgments": change_acknowledgments if change_acknowledgments else None,
        "divergence_acknowledgments": divergence_acknowledgments if divergence_acknowledgments else None,
    }


def create_outlier_analysis(
    guideline_id: str,
    batch: int,
    comparison_data: dict,
    analysis_summary: str,
    overall_recommendation: str,
    categorization_verdict_all_rust: str | None,
    categorization_reasoning_all_rust: str | None,
    categorization_verdict_safe_rust: str | None,
    categorization_reasoning_safe_rust: str | None,
    # Change acknowledgments (mapping -> decision)
    ack_change_applicability_all_rust: str | None,
    ack_change_applicability_safe_rust: str | None,
    ack_change_rationale_all_rust: str | None,
    ack_change_rationale_safe_rust: str | None,
    ack_change_category_all_rust: str | None,
    ack_change_category_safe_rust: str | None,
    # Divergence acknowledgments (decision -> ADD-6)
    ack_diverge_applicability_all_rust: str | None,
    ack_diverge_applicability_safe_rust: str | None,
    ack_diverge_category_all_rust: str | None,
    ack_diverge_category_safe_rust: str | None,
    # FLS changes
    fls_removals_verdict: str | None,
    fls_removals_reasoning: str | None,
    fls_removal_details: list[tuple[str, str, str]],  # (fls_id, context, justification)
    fls_additions_verdict: str | None,
    fls_additions_reasoning: str | None,
    fls_addition_details: list[tuple[str, str, str]],  # (fls_id, context, justification)
    add6_divergence_verdict: str | None,
    add6_divergence_reasoning: str | None,
    specificity_verdict: str | None,
    specificity_reasoning: str | None,
    routine_pattern: str | None,
    notes: str | None,
    general_recommendation: str | None,
    root: Path | None = None,
) -> dict:
    """
    Create outlier analysis structure with enriched FLS content and per-aspect verdicts.
    
    Returns the complete outlier analysis dict.
    """
    # Enrich FLS matches with content
    enriched_decision_ar = []
    for match in comparison_data["decision"]["all_rust"].get("accepted_matches", []):
        enriched_decision_ar.append(enrich_match_with_fls_content(match, root))
    
    enriched_decision_sr = []
    for match in comparison_data["decision"]["safe_rust"].get("accepted_matches", []):
        enriched_decision_sr.append(enrich_match_with_fls_content(match, root))
    
    enriched_mapping_ar = []
    for match in comparison_data["mapping"]["all_rust"].get("accepted_matches", []):
        enriched_mapping_ar.append(enrich_match_with_fls_content(match, root))
    
    enriched_mapping_sr = []
    for match in comparison_data["mapping"]["safe_rust"].get("accepted_matches", []):
        enriched_mapping_sr.append(enrich_match_with_fls_content(match, root))
    
    # Extract context metadata (applicability, rationale_type, adjusted_category per context)
    # This data is needed for per-context categorization review
    context_metadata = {
        "decision": {
            "all_rust": {
                "applicability": comparison_data["decision"]["all_rust"].get("applicability"),
                "rationale_type": comparison_data["decision"]["all_rust"].get("rationale_type"),
                "adjusted_category": comparison_data["decision"]["all_rust"].get("adjusted_category"),
            },
            "safe_rust": {
                "applicability": comparison_data["decision"]["safe_rust"].get("applicability"),
                "rationale_type": comparison_data["decision"]["safe_rust"].get("rationale_type"),
                "adjusted_category": comparison_data["decision"]["safe_rust"].get("adjusted_category"),
            },
        },
        "mapping": {
            "all_rust": {
                "applicability": comparison_data["mapping"]["all_rust"].get("applicability"),
                "rationale_type": comparison_data["mapping"]["all_rust"].get("rationale_type"),
                "adjusted_category": comparison_data["mapping"]["all_rust"].get("adjusted_category"),
            },
            "safe_rust": {
                "applicability": comparison_data["mapping"]["safe_rust"].get("applicability"),
                "rationale_type": comparison_data["mapping"]["safe_rust"].get("rationale_type"),
                "adjusted_category": comparison_data["mapping"]["safe_rust"].get("adjusted_category"),
            },
        },
    }
    
    # Build per-ID structures for removals
    # Structure: {fls_id: {title, category, contexts: [...], original_reason, removal_decisions: {ctx: justification}}}
    fls_removals_per_id = {}
    comparison = comparison_data.get("comparison", {})
    for ctx in ["all_rust", "safe_rust"]:
        for fls_id in comparison.get(ctx, {}).get("fls_removed", []):
            if fls_id not in fls_removals_per_id:
                # Find the original match info from mapping
                original_reason = None
                original_title = None
                original_category = None
                for match in comparison_data["mapping"].get(ctx, {}).get("accepted_matches", []):
                    if match.get("fls_id") == fls_id:
                        original_reason = match.get("reason")
                        original_title = match.get("fls_title")
                        original_category = match.get("category")
                        break
                fls_removals_per_id[fls_id] = {
                    "title": original_title,
                    "category": original_category,
                    "contexts": [ctx],
                    "original_reason": original_reason,
                    "removal_decisions": {},  # {context: justification}
                }
            else:
                # FLS ID already exists, add this context
                if ctx not in fls_removals_per_id[fls_id]["contexts"]:
                    fls_removals_per_id[fls_id]["contexts"].append(ctx)
    
    # Apply provided removal justifications (per context)
    for fls_id, context, justification in fls_removal_details:
        if fls_id in fls_removals_per_id:
            if context == "both":
                # Apply to both contexts if FLS ID exists in both
                for ctx in fls_removals_per_id[fls_id]["contexts"]:
                    fls_removals_per_id[fls_id]["removal_decisions"][ctx] = justification
            elif context in fls_removals_per_id[fls_id]["contexts"]:
                fls_removals_per_id[fls_id]["removal_decisions"][context] = justification
            else:
                print(f"WARNING: FLS ID {fls_id} not in context {context} for removals", file=sys.stderr)
    
    # Build per-ID structures for additions
    # Structure: {fls_id: {title, category, contexts: [...], new_reason, addition_decisions: {ctx: justification}}}
    fls_additions_per_id = {}
    for ctx in ["all_rust", "safe_rust"]:
        for fls_id in comparison.get(ctx, {}).get("fls_added", []):
            if fls_id not in fls_additions_per_id:
                # Find the new match info from decision
                new_reason = None
                new_title = None
                new_category = None
                for match in comparison_data["decision"].get(ctx, {}).get("accepted_matches", []):
                    if match.get("fls_id") == fls_id:
                        new_reason = match.get("reason")
                        new_title = match.get("fls_title")
                        new_category = match.get("category")
                        break
                fls_additions_per_id[fls_id] = {
                    "title": new_title,
                    "category": new_category,
                    "contexts": [ctx],
                    "new_reason": new_reason,
                    "addition_decisions": {},  # {context: justification}
                }
            else:
                # FLS ID already exists, add this context
                if ctx not in fls_additions_per_id[fls_id]["contexts"]:
                    fls_additions_per_id[fls_id]["contexts"].append(ctx)
    
    # Apply provided addition justifications (per context)
    for fls_id, context, justification in fls_addition_details:
        if fls_id in fls_additions_per_id:
            if context == "both":
                # Apply to both contexts if FLS ID exists in both
                for ctx in fls_additions_per_id[fls_id]["contexts"]:
                    fls_additions_per_id[fls_id]["addition_decisions"][ctx] = justification
            elif context in fls_additions_per_id[fls_id]["contexts"]:
                fls_additions_per_id[fls_id]["addition_decisions"][context] = justification
            else:
                print(f"WARNING: FLS ID {fls_id} not in context {context} for additions", file=sys.stderr)
    
    flags = comparison_data.get("flags", {})
    active_flags = get_active_flags(flags)
    
    # Build per-context categorization with acknowledgments
    categorization_all_rust = build_categorization_per_context(
        "all_rust",
        comparison_data,
        categorization_verdict_all_rust,
        categorization_reasoning_all_rust,
        ack_change_applicability_all_rust,
        ack_change_rationale_all_rust,
        ack_change_category_all_rust,
        ack_diverge_applicability_all_rust,
        ack_diverge_category_all_rust,
    ) if categorization_verdict_all_rust else None
    
    categorization_safe_rust = build_categorization_per_context(
        "safe_rust",
        comparison_data,
        categorization_verdict_safe_rust,
        categorization_reasoning_safe_rust,
        ack_change_applicability_safe_rust,
        ack_change_rationale_safe_rust,
        ack_change_category_safe_rust,
        ack_diverge_applicability_safe_rust,
        ack_diverge_category_safe_rust,
    ) if categorization_verdict_safe_rust else None
    
    return {
        "guideline_id": guideline_id,
        "batch": batch,
        "extraction_date": comparison_data.get("extraction_date", datetime.utcnow().isoformat() + "Z"),
        "analysis_date": datetime.utcnow().isoformat() + "Z",
        
        # Core comparison data
        "guideline_type": comparison_data.get("guideline_type", "Unknown"),
        "misra_chapter": comparison_data.get("misra_chapter", 0),
        "add6": comparison_data.get("add6", {}),
        "flags": flags,
        "active_flags": active_flags,
        
        # Comparison details
        "comparison": comparison,
        
        # Context metadata (applicability, rationale_type, adjusted_category per context)
        # Used for per-context categorization review
        "context_metadata": context_metadata,
        
        # Enriched FLS content
        "enriched_matches": {
            "mapping": {
                "all_rust": enriched_mapping_ar,
                "safe_rust": enriched_mapping_sr,
            },
            "decision": {
                "all_rust": enriched_decision_ar,
                "safe_rust": enriched_decision_sr,
            },
        },
        
        # LLM analysis with per-aspect verdicts
        "llm_analysis": {
            "summary": analysis_summary,
            "overall_recommendation": overall_recommendation,
            "analyzed_at": datetime.utcnow().isoformat() + "Z",
            
            "categorization": {
                "all_rust": categorization_all_rust,
                "safe_rust": categorization_safe_rust,
            } if (categorization_all_rust or categorization_safe_rust) else None,
            
            "fls_removals": {
                "verdict": fls_removals_verdict,
                "reasoning": fls_removals_reasoning,
                "per_id": fls_removals_per_id if fls_removals_per_id else None,
            } if fls_removals_verdict else None,
            
            "fls_additions": {
                "verdict": fls_additions_verdict,
                "reasoning": fls_additions_reasoning,
                "per_id": fls_additions_per_id if fls_additions_per_id else None,
            } if fls_additions_verdict else None,
            
            "add6_divergence": {
                "verdict": add6_divergence_verdict,
                "reasoning": add6_divergence_reasoning,
            } if add6_divergence_verdict else None,
            
            "specificity": {
                "verdict": specificity_verdict,
                "reasoning": specificity_reasoning,
                "lost_paragraphs": comparison.get("all_rust", {}).get("lost_paragraphs", []) +
                                   comparison.get("safe_rust", {}).get("lost_paragraphs", []),
            } if specificity_verdict else None,
            
            "routine_pattern": routine_pattern,
            "notes": notes,
            "general_recommendation": general_recommendation,
        },
        
        # Human review section (populated by review-outliers)
        "human_review": None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Record LLM analysis for a flagged guideline with per-aspect verdicts."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    parser.add_argument(
        "--guideline",
        required=True,
        help="Guideline ID (e.g., 'Rule 10.1')",
    )
    parser.add_argument(
        "--batch",
        required=True,
        type=int,
        help="Batch number the guideline belongs to",
    )
    
    # Overall analysis
    parser.add_argument(
        "--analysis-summary",
        required=True,
        help="Brief summary of MISRA concern and how Rust handles it",
    )
    parser.add_argument(
        "--overall-recommendation",
        required=True,
        choices=["accept", "accept_with_notes", "needs_review", "reject"],
        help="Overall recommendation for the decision",
    )
    
    # Categorization verdict (per-context)
    parser.add_argument(
        "--categorization-verdict-all-rust",
        choices=["appropriate", "inappropriate", "needs_review", "n_a"],
        help="Verdict on all_rust categorization (applicability, category, rationale type)",
    )
    parser.add_argument(
        "--categorization-reasoning-all-rust",
        help="Reasoning for all_rust categorization verdict",
    )
    parser.add_argument(
        "--categorization-verdict-safe-rust",
        choices=["appropriate", "inappropriate", "needs_review", "n_a"],
        help="Verdict on safe_rust categorization (applicability, category, rationale type)",
    )
    parser.add_argument(
        "--categorization-reasoning-safe-rust",
        help="Reasoning for safe_rust categorization verdict",
    )
    
    # Change acknowledgments (mapping -> decision)
    # Required when the corresponding change flag is set in comparison data
    parser.add_argument(
        "--cat-ack-change-applicability-all-rust",
        help="Acknowledge applicability change for all_rust (required if changed)",
    )
    parser.add_argument(
        "--cat-ack-change-applicability-safe-rust",
        help="Acknowledge applicability change for safe_rust (required if changed)",
    )
    parser.add_argument(
        "--cat-ack-change-rationale-all-rust",
        help="Acknowledge rationale_type change for all_rust (required if changed)",
    )
    parser.add_argument(
        "--cat-ack-change-rationale-safe-rust",
        help="Acknowledge rationale_type change for safe_rust (required if changed)",
    )
    parser.add_argument(
        "--cat-ack-change-category-all-rust",
        help="Acknowledge adjusted_category change for all_rust (required if changed)",
    )
    parser.add_argument(
        "--cat-ack-change-category-safe-rust",
        help="Acknowledge adjusted_category change for safe_rust (required if changed)",
    )
    
    # Divergence acknowledgments (decision -> ADD-6)
    # Required when the corresponding divergence flag is set in comparison data
    parser.add_argument(
        "--cat-ack-diverge-applicability-all-rust",
        help="Acknowledge applicability diverges from ADD-6 for all_rust (required if diverges)",
    )
    parser.add_argument(
        "--cat-ack-diverge-applicability-safe-rust",
        help="Acknowledge applicability diverges from ADD-6 for safe_rust (required if diverges)",
    )
    parser.add_argument(
        "--cat-ack-diverge-category-all-rust",
        help="Acknowledge adjusted_category diverges from ADD-6 for all_rust (required if diverges)",
    )
    parser.add_argument(
        "--cat-ack-diverge-category-safe-rust",
        help="Acknowledge adjusted_category diverges from ADD-6 for safe_rust (required if diverges)",
    )
    
    # FLS removals verdict
    parser.add_argument(
        "--fls-removals-verdict",
        choices=["appropriate", "inappropriate", "needs_review", "n_a"],
        help="Verdict on FLS section removals",
    )
    parser.add_argument(
        "--fls-removals-reasoning",
        help="Overall reasoning for FLS removals verdict",
    )
    parser.add_argument(
        "--fls-removal-detail",
        action="append",
        default=[],
        metavar="FLS_ID:JUSTIFICATION",
        help="Per-FLS-ID removal justification (can be repeated)",
    )
    
    # FLS additions verdict
    parser.add_argument(
        "--fls-additions-verdict",
        choices=["appropriate", "inappropriate", "needs_review", "n_a"],
        help="Verdict on FLS section additions (when 2+ added)",
    )
    parser.add_argument(
        "--fls-additions-reasoning",
        help="Overall reasoning for FLS additions verdict",
    )
    parser.add_argument(
        "--fls-addition-detail",
        action="append",
        default=[],
        metavar="FLS_ID:JUSTIFICATION",
        help="Per-FLS-ID addition justification (can be repeated)",
    )
    
    # ADD-6 divergence verdict
    parser.add_argument(
        "--add6-divergence-verdict",
        choices=["justified", "questionable", "incorrect", "n_a"],
        help="Verdict on divergence from ADD-6 categorization",
    )
    parser.add_argument(
        "--add6-divergence-reasoning",
        help="Reasoning for ADD-6 divergence verdict",
    )
    
    # Specificity verdict (when paragraph-level matches were lost)
    parser.add_argument(
        "--specificity-verdict",
        choices=["appropriate", "inappropriate", "needs_review", "n_a"],
        help="Verdict on loss of paragraph-level specificity",
    )
    parser.add_argument(
        "--specificity-reasoning",
        help="Reasoning for specificity verdict (required when specificity_decreased flag is set)",
    )
    
    # Optional
    parser.add_argument(
        "--routine-pattern",
        help="If this is a routine pattern (e.g., 'generic section removal')",
    )
    parser.add_argument(
        "--notes",
        help="Additional notes",
    )
    parser.add_argument(
        "--general-recommendation",
        help="General recommendation applicable to similar guidelines (if any)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing analysis",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without saving",
    )
    
    args = parser.parse_args()
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    # Load comparison data
    comparison_data = load_comparison_data(args.guideline, args.batch, root)
    if not comparison_data:
        print(f"ERROR: No comparison data found for {args.guideline} in batch {args.batch}", file=sys.stderr)
        print(f"  Run: uv run extract-comparison-data --standard {args.standard} --batches {args.batch}", file=sys.stderr)
        sys.exit(1)
    
    # Check if analysis already exists
    existing = load_outlier_analysis(args.guideline, root)
    if existing and not args.force:
        print(f"ERROR: Analysis already exists for {args.guideline}", file=sys.stderr)
        print(f"  Use --force to overwrite", file=sys.stderr)
        sys.exit(1)
    
    # Parse FLS detail arguments
    fls_removal_details = []
    for detail in args.fls_removal_detail:
        try:
            fls_removal_details.append(parse_fls_detail(detail))
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    fls_addition_details = []
    for detail in args.fls_addition_detail:
        try:
            fls_addition_details.append(parse_fls_detail(detail))
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Validate FLS detail justifications (min length, must quote FLS)
    fls_detail_errors = []
    for fls_id, context, justification in fls_removal_details:
        fls_detail_errors.extend(validate_fls_detail_justification(fls_id, justification, "removal"))
    for fls_id, context, justification in fls_addition_details:
        fls_detail_errors.extend(validate_fls_detail_justification(fls_id, justification, "addition"))
    
    if fls_detail_errors:
        print(f"ERROR: FLS detail justification validation failed:", file=sys.stderr)
        for err in fls_detail_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    
    # Validate conditional requirements based on flags
    flags = comparison_data.get("flags", {})
    comparison = comparison_data.get("comparison", {})
    validation_errors = []
    
    # Categorization verdict required if rationale_type_changed or batch_pattern_outlier (per-context)
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        if not args.categorization_verdict_all_rust:
            validation_errors.append("Missing --categorization-verdict-all-rust (required: rationale_type_changed or batch_pattern_outlier flag set)")
        if not args.categorization_verdict_safe_rust:
            validation_errors.append("Missing --categorization-verdict-safe-rust (required: rationale_type_changed or batch_pattern_outlier flag set)")
    
    # FLS removals verdict required if fls_removed
    if flags.get("fls_removed") and not args.fls_removals_verdict:
        validation_errors.append("Missing --fls-removals-verdict (required: fls_removed flag set)")
    
    # FLS additions verdict required if fls_added
    if flags.get("fls_added") and not args.fls_additions_verdict:
        validation_errors.append("Missing --fls-additions-verdict (required: fls_added flag set)")
    
    # ADD-6 divergence verdict required if divergence flags, and n_a is not valid
    has_add6_divergence = flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6")
    if has_add6_divergence:
        if not args.add6_divergence_verdict:
            validation_errors.append("Missing --add6-divergence-verdict (required: ADD-6 divergence flag set)")
        elif args.add6_divergence_verdict == "n_a":
            diverging = get_diverging_contexts(comparison, comparison_data.get("add6", {}))
            validation_errors.append(
                f"Cannot use 'n_a' for --add6-divergence-verdict when divergence flag is set. "
                f"Use 'justified', 'questionable', or 'incorrect'. "
                f"Diverging contexts: {', '.join(diverging)}"
            )
    
    # Specificity verdict required if specificity_decreased flag
    if flags.get("specificity_decreased") and not args.specificity_verdict:
        validation_errors.append("Missing --specificity-verdict (required: specificity_decreased flag set)")
    
    # Validate per-context change acknowledgments
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        ctx_flag = ctx.replace("_", "-")  # for CLI flag names
        
        # Applicability change acknowledgment
        if ctx_comp.get("applicability_changed"):
            ack_val = getattr(args, f"cat_ack_change_applicability_{ctx}")
            if not ack_val:
                validation_errors.append(
                    f"Missing --cat-ack-change-applicability-{ctx_flag} "
                    f"(required: comparison.{ctx}.applicability_changed is true)"
                )
            elif len(ack_val) < MIN_ACK_LENGTH:
                validation_errors.append(
                    f"--cat-ack-change-applicability-{ctx_flag} too short "
                    f"(min {MIN_ACK_LENGTH} chars, got {len(ack_val)})"
                )
        
        # Rationale type change acknowledgment
        if ctx_comp.get("rationale_type_changed"):
            ack_val = getattr(args, f"cat_ack_change_rationale_{ctx}")
            if not ack_val:
                validation_errors.append(
                    f"Missing --cat-ack-change-rationale-{ctx_flag} "
                    f"(required: comparison.{ctx}.rationale_type_changed is true)"
                )
            elif len(ack_val) < MIN_ACK_LENGTH:
                validation_errors.append(
                    f"--cat-ack-change-rationale-{ctx_flag} too short "
                    f"(min {MIN_ACK_LENGTH} chars, got {len(ack_val)})"
                )
        
        # Adjusted category change acknowledgment
        if ctx_comp.get("adjusted_category_changed"):
            ack_val = getattr(args, f"cat_ack_change_category_{ctx}")
            if not ack_val:
                validation_errors.append(
                    f"Missing --cat-ack-change-category-{ctx_flag} "
                    f"(required: comparison.{ctx}.adjusted_category_changed is true)"
                )
            elif len(ack_val) < MIN_ACK_LENGTH:
                validation_errors.append(
                    f"--cat-ack-change-category-{ctx_flag} too short "
                    f"(min {MIN_ACK_LENGTH} chars, got {len(ack_val)})"
                )
        
        # Applicability divergence acknowledgment
        if ctx_comp.get("applicability_differs_from_add6"):
            ack_val = getattr(args, f"cat_ack_diverge_applicability_{ctx}")
            if not ack_val:
                validation_errors.append(
                    f"Missing --cat-ack-diverge-applicability-{ctx_flag} "
                    f"(required: comparison.{ctx}.applicability_differs_from_add6 is true)"
                )
            elif len(ack_val) < MIN_ACK_LENGTH:
                validation_errors.append(
                    f"--cat-ack-diverge-applicability-{ctx_flag} too short "
                    f"(min {MIN_ACK_LENGTH} chars, got {len(ack_val)})"
                )
        
        # Adjusted category divergence acknowledgment
        if ctx_comp.get("adjusted_category_differs_from_add6"):
            ack_val = getattr(args, f"cat_ack_diverge_category_{ctx}")
            if not ack_val:
                validation_errors.append(
                    f"Missing --cat-ack-diverge-category-{ctx_flag} "
                    f"(required: comparison.{ctx}.adjusted_category_differs_from_add6 is true)"
                )
            elif len(ack_val) < MIN_ACK_LENGTH:
                validation_errors.append(
                    f"--cat-ack-diverge-category-{ctx_flag} too short "
                    f"(min {MIN_ACK_LENGTH} chars, got {len(ack_val)})"
                )
    
    # Validate per-ID coverage for removals
    all_removed_ids = set()
    for ctx in ["all_rust", "safe_rust"]:
        all_removed_ids.update(comparison.get(ctx, {}).get("fls_removed", []))
    
    provided_removal_ids = {fls_id for fls_id, _, _ in fls_removal_details}
    missing_removal_details = all_removed_ids - provided_removal_ids
    if missing_removal_details:
        validation_errors.append(
            f"Missing --fls-removal-detail for: {', '.join(sorted(missing_removal_details))}"
        )
    
    # Validate per-ID coverage for additions
    all_added_ids = set()
    for ctx in ["all_rust", "safe_rust"]:
        all_added_ids.update(comparison.get(ctx, {}).get("fls_added", []))
    
    provided_addition_ids = {fls_id for fls_id, _, _ in fls_addition_details}
    missing_addition_details = all_added_ids - provided_addition_ids
    if missing_addition_details:
        validation_errors.append(
            f"Missing --fls-addition-detail for: {', '.join(sorted(missing_addition_details))}"
        )
    
    # Handle validation errors
    if validation_errors:
        print(f"ERROR: {args.guideline} has validation errors:", file=sys.stderr)
        for err in validation_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    
    # Create analysis
    analysis = create_outlier_analysis(
        args.guideline,
        args.batch,
        comparison_data,
        args.analysis_summary,
        args.overall_recommendation,
        args.categorization_verdict_all_rust,
        args.categorization_reasoning_all_rust,
        args.categorization_verdict_safe_rust,
        args.categorization_reasoning_safe_rust,
        # Change acknowledgments
        args.cat_ack_change_applicability_all_rust,
        args.cat_ack_change_applicability_safe_rust,
        args.cat_ack_change_rationale_all_rust,
        args.cat_ack_change_rationale_safe_rust,
        args.cat_ack_change_category_all_rust,
        args.cat_ack_change_category_safe_rust,
        # Divergence acknowledgments
        args.cat_ack_diverge_applicability_all_rust,
        args.cat_ack_diverge_applicability_safe_rust,
        args.cat_ack_diverge_category_all_rust,
        args.cat_ack_diverge_category_safe_rust,
        # FLS changes
        args.fls_removals_verdict,
        args.fls_removals_reasoning,
        fls_removal_details,
        args.fls_additions_verdict,
        args.fls_additions_reasoning,
        fls_addition_details,
        args.add6_divergence_verdict,
        args.add6_divergence_reasoning,
        args.specificity_verdict,
        args.specificity_reasoning,
        args.routine_pattern,
        args.notes,
        args.general_recommendation,
        root,
    )
    
    if args.dry_run:
        import json
        print("Would write analysis:")
        print(json.dumps(analysis, indent=2))
        return
    
    # Save
    output_path = save_outlier_analysis(args.guideline, analysis, root)
    print(f"Saved analysis to: {output_path}")
    print(f"  Guideline: {args.guideline}")
    print(f"  Recommendation: {args.overall_recommendation}")
    print(f"  Active flags: {', '.join(analysis['active_flags'])}")


if __name__ == "__main__":
    main()
