#!/usr/bin/env python3
"""
prepare-outlier-analysis - Display full context for analyzing ONE guideline.

This tool forces single-guideline focus by displaying:
- Full comparison data (mapping vs decision vs ADD-6)
- Actual FLS content for all removed/added sections (including rubrics)
- Required acknowledgment flags based on active flags
- Template command with all required arguments

The output is designed to force the analyst to read actual FLS text before
making judgments, preventing shallow pattern-matching across guidelines.

Usage:
    uv run prepare-outlier-analysis --standard misra-c --guideline "Rule 9.7" --batch 1
"""

import argparse
import sys
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    load_comparison_data,
    load_fls_content,
    get_active_flags,
    guideline_to_filename,
)


# Rubric category names
RUBRIC_NAMES = {
    "-1": "GENERAL",
    "-2": "LEGALITY RULES",
    "-3": "DYNAMIC SEMANTICS",
    "-4": "UNDEFINED BEHAVIOR",
    "-5": "IMPLEMENTATION REQUIREMENTS",
    "-6": "IMPLEMENTATION PERMISSIONS",
    "-7": "EXAMPLES",
    "-8": "SYNTAX",
}


def format_box(content: str, width: int = 76) -> str:
    """Format content in a box with borders."""
    lines = content.split("\n")
    result = ["┌" + "─" * width + "┐"]
    for line in lines:
        # Truncate long lines
        if len(line) > width - 2:
            line = line[: width - 5] + "..."
        result.append("│ " + line.ljust(width - 2) + " │")
    result.append("└" + "─" * width + "┘")
    return "\n".join(result)


def format_fls_content(fls_id: str, root: Path | None = None) -> str:
    """Format FLS section content with all rubrics."""
    content = load_fls_content(fls_id, root)
    if not content:
        return f"      (FLS content not found for {fls_id})"

    lines = []

    # Main content
    main_content = content.get("content", "").strip()
    if main_content:
        # Show first 500 chars of main content
        preview = main_content[:500]
        if len(main_content) > 500:
            preview += "..."
        lines.append("      FLS CONTENT:")
        for line in preview.split("\n"):
            lines.append(f"      │ {line}")

    # Rubrics
    rubrics = content.get("rubrics", {})
    for cat_code in sorted(rubrics.keys(), key=lambda x: int(x)):
        cat_name = RUBRIC_NAMES.get(cat_code, f"CATEGORY {cat_code}")
        paragraphs = rubrics[cat_code]
        if paragraphs:
            lines.append(f"")
            lines.append(f"      {cat_name} ({cat_code}):")
            for i, para in enumerate(paragraphs[:5], 1):  # Show up to 5 paragraphs
                # Truncate long paragraphs
                para_text = para.strip()
                if len(para_text) > 200:
                    para_text = para_text[:200] + "..."
                lines.append(f"        • {para_text}")
            if len(paragraphs) > 5:
                lines.append(f"        ... and {len(paragraphs) - 5} more paragraphs")

    return "\n".join(lines)


def print_context_section(
    ctx_name: str,
    comparison: dict,
    mapping_ctx: dict,
    decision_ctx: dict,
    add6: dict,
    root: Path,
) -> None:
    """Print the analysis section for one context (all_rust or safe_rust)."""
    print(f"\n{'-' * 80}")
    print(f"CONTEXT: {ctx_name}")
    print(f"{'-' * 80}")

    # Values summary
    dec_app = decision_ctx.get("applicability", "?")
    dec_rat = decision_ctx.get("rationale_type", "?")
    dec_cat = decision_ctx.get("adjusted_category", "?")

    map_app = mapping_ctx.get("applicability", "?")
    map_rat = mapping_ctx.get("rationale_type", "?")
    map_cat = mapping_ctx.get("adjusted_category", "?")

    add6_key = f"applicability_{ctx_name}"
    add6_app = add6.get(add6_key, "?")
    add6_cat = add6.get("adjusted_category", "?")

    print(f"Decision: applicability={dec_app}, rationale_type={dec_rat}, adjusted_category={dec_cat}")
    print(f"Mapping:  applicability={map_app}, rationale_type={map_rat}, adjusted_category={map_cat}")
    print(f"ADD-6:    applicability={add6_app}, adjusted_category={add6_cat}")

    # Changes from mapping
    changes = []
    if comparison.get("applicability_changed"):
        changes.append(f"applicability: {comparison.get('applicability_mapping_to_decision')}")
    if comparison.get("rationale_type_changed"):
        changes.append(f"rationale_type: {comparison.get('rationale_type_mapping_to_decision')}")
    if comparison.get("adjusted_category_changed"):
        changes.append(f"adjusted_category: {comparison.get('adjusted_category_mapping_to_decision')}")

    if changes:
        print(f"\nChanges from mapping:")
        for c in changes:
            print(f"  • {c}")
    else:
        print(f"\nChanges from mapping: None")

    # Divergence from ADD-6
    divergences = []
    if comparison.get("applicability_differs_from_add6"):
        divergences.append(f"applicability: decision={dec_app}, ADD-6={add6_app}")
    if comparison.get("adjusted_category_differs_from_add6"):
        divergences.append(f"adjusted_category: decision={dec_cat}, ADD-6={add6_cat}")

    if divergences:
        print(f"\nDivergence from ADD-6:")
        for d in divergences:
            print(f"  ⚠ {d}")
    else:
        print(f"\nDivergence from ADD-6: None")

    # FLS Removed
    fls_removed = comparison.get("fls_removed", [])
    if fls_removed:
        print(f"\nFLS REMOVED (from mapping → not in decision): {len(fls_removed)} section(s)")
        for i, fls_id in enumerate(fls_removed, 1):
            # Find original match info from mapping
            original_match = None
            for m in mapping_ctx.get("accepted_matches", []):
                if m.get("fls_id") == fls_id:
                    original_match = m
                    break

            title = original_match.get("fls_title", "?") if original_match else "?"
            category = original_match.get("category", 0) if original_match else 0
            score = original_match.get("score", 0) if original_match else 0
            reason = original_match.get("reason", "") if original_match else ""

            print(f"\n  [{i}] {fls_id} - \"{title}\" (category: {category}, score: {score:.2f})")
            if reason:
                print(f"      Mapping reason: \"{reason[:200]}{'...' if len(reason) > 200 else ''}\"")

            # Show FLS content
            print(format_fls_content(fls_id, root))

    # FLS Added
    fls_added = comparison.get("fls_added", [])
    if fls_added:
        print(f"\nFLS ADDED (in decision → not in mapping): {len(fls_added)} section(s)")
        for i, fls_id in enumerate(fls_added, 1):
            # Find new match info from decision
            new_match = None
            for m in decision_ctx.get("accepted_matches", []):
                if m.get("fls_id") == fls_id:
                    new_match = m
                    break

            title = new_match.get("fls_title", "?") if new_match else "?"
            category = new_match.get("category", 0) if new_match else 0
            score = new_match.get("score", 0) if new_match else 0
            reason = new_match.get("reason", "") if new_match else ""

            print(f"\n  [{i}] {fls_id} - \"{title}\" (category: {category}, score: {score:.2f})")
            if reason:
                print(f"      Decision reason: \"{reason[:200]}{'...' if len(reason) > 200 else ''}\"")

            # Show FLS content
            print(format_fls_content(fls_id, root))

    # Lost paragraphs (specificity)
    lost_paragraphs = comparison.get("lost_paragraphs", [])
    if lost_paragraphs:
        print(f"\nSPECIFICITY LOSS: Lost {len(lost_paragraphs)} paragraph-level match(es)")
        for lp in lost_paragraphs:
            print(f"  • {lp.get('fls_id')} - \"{lp.get('fls_title')}\" (category: {lp.get('category')})")


def collect_required_flags(comparison_data: dict) -> list[str]:
    """Collect list of required CLI flags based on comparison data."""
    required = []
    comparison = comparison_data.get("comparison", {})
    flags = comparison_data.get("flags", {})

    for ctx in ["all_rust", "safe_rust"]:
        ctx_flag = ctx.replace("_", "-")
        ctx_comp = comparison.get(ctx, {})

        # Change acknowledgments
        if ctx_comp.get("applicability_changed"):
            required.append(f'--cat-ack-change-applicability-{ctx_flag} "FILL"')
        if ctx_comp.get("rationale_type_changed"):
            required.append(f'--cat-ack-change-rationale-{ctx_flag} "FILL"')
        if ctx_comp.get("adjusted_category_changed"):
            required.append(f'--cat-ack-change-category-{ctx_flag} "FILL"')

        # Divergence acknowledgments
        if ctx_comp.get("applicability_differs_from_add6"):
            required.append(f'--cat-ack-diverge-applicability-{ctx_flag} "FILL"')
        if ctx_comp.get("adjusted_category_differs_from_add6"):
            required.append(f'--cat-ack-diverge-category-{ctx_flag} "FILL"')

    # FLS removal details
    all_removed = set()
    for ctx in ["all_rust", "safe_rust"]:
        all_removed.update(comparison.get(ctx, {}).get("fls_removed", []))
    for fls_id in sorted(all_removed):
        # Determine which context(s) this removal applies to
        contexts = []
        for ctx in ["all_rust", "safe_rust"]:
            if fls_id in comparison.get(ctx, {}).get("fls_removed", []):
                contexts.append(ctx)
        ctx_str = "both" if len(contexts) == 2 else contexts[0]
        required.append(f'--fls-removal-detail "{fls_id}:{ctx_str}:FILL"')

    # FLS addition details
    all_added = set()
    for ctx in ["all_rust", "safe_rust"]:
        all_added.update(comparison.get(ctx, {}).get("fls_added", []))
    for fls_id in sorted(all_added):
        contexts = []
        for ctx in ["all_rust", "safe_rust"]:
            if fls_id in comparison.get(ctx, {}).get("fls_added", []):
                contexts.append(ctx)
        ctx_str = "both" if len(contexts) == 2 else contexts[0]
        required.append(f'--fls-addition-detail "{fls_id}:{ctx_str}:FILL"')

    return required


def generate_template_command(
    guideline_id: str, batch: int, comparison_data: dict
) -> str:
    """Generate template record command with all required flags."""
    flags = comparison_data.get("flags", {})
    comparison = comparison_data.get("comparison", {})

    lines = [
        f'uv run record-outlier-analysis --standard misra-c --guideline "{guideline_id}" --batch {batch} \\\\'
    ]

    # Required fields
    lines.append('    --analysis-summary "FILL: 1-2 sentence summary of MISRA concern and Rust handling" \\\\')
    lines.append("    --overall-recommendation FILL \\\\")

    # Categorization (always required when batch_pattern_outlier or rationale_type_changed)
    lines.append("    --categorization-verdict-all-rust FILL \\\\")
    lines.append('    --categorization-reasoning-all-rust "FILL" \\\\')
    lines.append("    --categorization-verdict-safe-rust FILL \\\\")
    lines.append('    --categorization-reasoning-safe-rust "FILL" \\\\')

    # Context-specific acknowledgments
    for ctx in ["all_rust", "safe_rust"]:
        ctx_flag = ctx.replace("_", "-")
        ctx_comp = comparison.get(ctx, {})

        if ctx_comp.get("applicability_changed"):
            lines.append(f'    --cat-ack-change-applicability-{ctx_flag} "FILL: Why did applicability change?" \\\\')
        if ctx_comp.get("rationale_type_changed"):
            lines.append(f'    --cat-ack-change-rationale-{ctx_flag} "FILL: Why did rationale_type change?" \\\\')
        if ctx_comp.get("adjusted_category_changed"):
            lines.append(f'    --cat-ack-change-category-{ctx_flag} "FILL: Why did adjusted_category change?" \\\\')
        if ctx_comp.get("applicability_differs_from_add6"):
            lines.append(f'    --cat-ack-diverge-applicability-{ctx_flag} "FILL: Why does applicability diverge from ADD-6?" \\\\')
        if ctx_comp.get("adjusted_category_differs_from_add6"):
            lines.append(f'    --cat-ack-diverge-category-{ctx_flag} "FILL: Why does adjusted_category diverge from ADD-6?" \\\\')

    # FLS removals
    if flags.get("fls_removed"):
        lines.append("    --fls-removals-verdict FILL \\\\")
        lines.append('    --fls-removals-reasoning "FILL" \\\\')

        all_removed = set()
        for ctx in ["all_rust", "safe_rust"]:
            all_removed.update(comparison.get(ctx, {}).get("fls_removed", []))
        for fls_id in sorted(all_removed):
            contexts = []
            for ctx in ["all_rust", "safe_rust"]:
                if fls_id in comparison.get(ctx, {}).get("fls_removed", []):
                    contexts.append(ctx)
            ctx_str = "both" if len(contexts) == 2 else contexts[0]
            lines.append(f'    --fls-removal-detail "{fls_id}:{ctx_str}:FILL (min 50 chars, must quote FLS)" \\\\')

    # FLS additions
    if flags.get("fls_added"):
        lines.append("    --fls-additions-verdict FILL \\\\")
        lines.append('    --fls-additions-reasoning "FILL" \\\\')

        all_added = set()
        for ctx in ["all_rust", "safe_rust"]:
            all_added.update(comparison.get(ctx, {}).get("fls_added", []))
        for fls_id in sorted(all_added):
            contexts = []
            for ctx in ["all_rust", "safe_rust"]:
                if fls_id in comparison.get(ctx, {}).get("fls_added", []):
                    contexts.append(ctx)
            ctx_str = "both" if len(contexts) == 2 else contexts[0]
            lines.append(f'    --fls-addition-detail "{fls_id}:{ctx_str}:FILL (min 50 chars, must quote FLS)" \\\\')

    # ADD-6 divergence
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        lines.append("    --add6-divergence-verdict FILL \\\\")
        lines.append('    --add6-divergence-reasoning "FILL" \\\\')

    # Specificity
    if flags.get("specificity_decreased"):
        lines.append("    --specificity-verdict FILL \\\\")
        lines.append('    --specificity-reasoning "FILL" \\\\')

    # General recommendation (optional)
    lines.append('    --general-recommendation "FILL or delete this line if none" \\\\')

    # Force flag
    lines.append("    --force")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Display full context for analyzing ONE outlier guideline."
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
        help="Guideline ID (e.g., 'Rule 9.7')",
    )
    parser.add_argument(
        "--batch",
        required=True,
        type=int,
        help="Batch number",
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

    # Extract key data
    add6 = comparison_data.get("add6", {})
    mapping = comparison_data.get("mapping", {})
    decision = comparison_data.get("decision", {})
    comparison = comparison_data.get("comparison", {})
    flags = comparison_data.get("flags", {})

    # Header
    print("=" * 80)
    print(f"OUTLIER ANALYSIS: {args.guideline} (Batch {args.batch})")
    print("=" * 80)

    # MISRA concern
    guideline_title = comparison_data.get("guideline_title", "")
    if guideline_title:
        print(f"\nMISRA CONCERN: {guideline_title}")

    # ADD-6 summary
    add6_all = add6.get("applicability_all_rust", "?")
    add6_safe = add6.get("applicability_safe_rust", "?")
    add6_cat = add6.get("adjusted_category", "?")
    add6_rationale = add6.get("rationale_codes", [])
    print(f"ADD-6: all_rust={add6_all}, safe_rust={add6_safe}, adjusted_category={add6_cat}, rationale={add6_rationale}")

    # Active flags
    active_flags = get_active_flags(flags)
    print(f"\nACTIVE FLAGS:")
    for flag in active_flags:
        # Add context details for some flags
        detail = ""
        if flag == "applicability_differs_from_add6":
            contexts = []
            if comparison.get("all_rust", {}).get("applicability_differs_from_add6"):
                contexts.append("all_rust")
            if comparison.get("safe_rust", {}).get("applicability_differs_from_add6"):
                contexts.append("safe_rust")
            detail = f" ({', '.join(contexts)})"
        elif flag == "adjusted_category_differs_from_add6":
            contexts = []
            if comparison.get("all_rust", {}).get("adjusted_category_differs_from_add6"):
                contexts.append("all_rust")
            if comparison.get("safe_rust", {}).get("adjusted_category_differs_from_add6"):
                contexts.append("safe_rust")
            detail = f" ({', '.join(contexts)})"
        elif flag == "fls_removed":
            count = len(set(comparison.get("all_rust", {}).get("fls_removed", []))
                       | set(comparison.get("safe_rust", {}).get("fls_removed", [])))
            detail = f" ({count} IDs)"
        elif flag == "fls_added":
            count = len(set(comparison.get("all_rust", {}).get("fls_added", []))
                       | set(comparison.get("safe_rust", {}).get("fls_added", [])))
            detail = f" ({count} IDs)"
        print(f"  ✓ {flag}{detail}")

    # Context sections
    print_context_section(
        "all_rust",
        comparison.get("all_rust", {}),
        mapping.get("all_rust", {}),
        decision.get("all_rust", {}),
        add6,
        root,
    )

    print_context_section(
        "safe_rust",
        comparison.get("safe_rust", {}),
        mapping.get("safe_rust", {}),
        decision.get("safe_rust", {}),
        add6,
        root,
    )

    # Required flags section
    required_flags = collect_required_flags(comparison_data)
    if required_flags:
        print(f"\n{'=' * 80}")
        print("REQUIRED FLAGS (based on active flags):")
        print("=" * 80)
        print("\nThe following acknowledgment/detail flags MUST be provided:\n")
        for flag in required_flags:
            print(f"  {flag}")

    # Template command
    print(f"\n{'=' * 80}")
    print("TEMPLATE COMMAND:")
    print("=" * 80)
    print()
    print(generate_template_command(args.guideline, args.batch, comparison_data))
    print()


if __name__ == "__main__":
    main()
