#!/usr/bin/env python3
"""
check-analysis-progress - Show progress and suggest next guideline for outlier analysis.

This tool provides:
1. Overall progress statistics (how many outliers analyzed across batches)
2. Per-batch breakdown with pending guidelines listed
3. Suggestion for next guideline to analyze (with prepare command)
4. Checkpoints every 5 guidelines analyzed

Usage:
    uv run check-analysis-progress --standard misra-c
    uv run check-analysis-progress --standard misra-c --batches 1,2
"""

import argparse
import sys
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_comparison_data_dir,
    get_outlier_analysis_dir,
    guideline_to_filename,
    filename_to_guideline,
    load_json_file,
    load_outlier_analysis,
    is_outlier,
    get_active_flags,
)


def get_batch_numbers(comparison_data_dir: Path) -> list[int]:
    """Get available batch numbers from comparison data directory."""
    batches = []
    for d in comparison_data_dir.iterdir():
        if d.is_dir() and d.name.startswith("batch"):
            try:
                batch_num = int(d.name.replace("batch", ""))
                batches.append(batch_num)
            except ValueError:
                continue
    return sorted(batches)


def get_outliers_in_batch(batch_dir: Path) -> list[str]:
    """Get list of guideline IDs that are outliers in a batch."""
    outliers = []
    for f in batch_dir.glob("*.json"):
        data = load_json_file(f)
        if data and data.get("flags"):
            if is_outlier(data.get("flags", {})):
                outliers.append(data.get("guideline_id", filename_to_guideline(f.name)))
    return sorted(outliers)


def check_analyzed(guideline_id: str, root: Path) -> dict | None:
    """Check if a guideline has been analyzed, return analysis if so."""
    return load_outlier_analysis(guideline_id, root)


def main():
    parser = argparse.ArgumentParser(
        description="Show outlier analysis progress and suggest next guideline."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to check progress for",
    )
    parser.add_argument(
        "--batches",
        help="Comma-separated batch numbers to check (default: all)",
    )
    parser.add_argument(
        "--suggest-next",
        action="store_true",
        default=True,
        help="Suggest next guideline to analyze (default: True)",
    )
    parser.add_argument(
        "--no-suggest-next",
        action="store_false",
        dest="suggest_next",
        help="Don't suggest next guideline",
    )

    args = parser.parse_args()

    standard = normalize_standard(args.standard)
    root = get_project_root()
    comparison_data_dir = get_comparison_data_dir(root)
    outlier_analysis_dir = get_outlier_analysis_dir(root)

    # Determine which batches to check
    all_batches = get_batch_numbers(comparison_data_dir)
    if args.batches:
        batches = [int(b.strip()) for b in args.batches.split(",")]
    else:
        batches = all_batches

    if not batches:
        print("ERROR: No batches found in comparison data directory.", file=sys.stderr)
        print(f"  Run: uv run extract-comparison-data --standard {standard} --batches 1,2,3", file=sys.stderr)
        sys.exit(1)

    # Collect statistics
    total_outliers = 0
    total_analyzed = 0
    batch_stats = {}
    first_pending = None  # Track first pending guideline for suggestion
    first_pending_batch = None

    print("=" * 70)
    print(f"OUTLIER ANALYSIS PROGRESS: {standard}")
    print("=" * 70)

    for batch in batches:
        batch_dir = comparison_data_dir / f"batch{batch}"
        if not batch_dir.exists():
            print(f"\nBatch {batch}: (no comparison data)")
            continue

        outliers = get_outliers_in_batch(batch_dir)
        analyzed = []
        pending = []

        for guideline_id in outliers:
            analysis = check_analyzed(guideline_id, root)
            if analysis:
                analyzed.append(guideline_id)
            else:
                pending.append(guideline_id)
                if first_pending is None:
                    first_pending = guideline_id
                    first_pending_batch = batch

        total_outliers += len(outliers)
        total_analyzed += len(analyzed)

        batch_stats[batch] = {
            "total": len(outliers),
            "analyzed": len(analyzed),
            "pending": len(pending),
            "pending_list": pending,
        }

        # Print batch summary
        pct = (len(analyzed) / len(outliers) * 100) if outliers else 0
        status = "✓ COMPLETE" if len(pending) == 0 else ""
        print(f"\nBatch {batch}: {len(analyzed)}/{len(outliers)} analyzed ({pct:.0f}%) {status}")
        
        if pending:
            print(f"  Pending ({len(pending)}):")
            for g in pending[:10]:  # Show first 10
                print(f"    - {g}")
            if len(pending) > 10:
                print(f"    ... and {len(pending) - 10} more")

    # Overall summary
    print(f"\n{'=' * 70}")
    overall_pct = (total_analyzed / total_outliers * 100) if total_outliers else 0
    print(f"OVERALL: {total_analyzed}/{total_outliers} analyzed ({overall_pct:.0f}%)")

    # Checkpoint reminder
    if total_analyzed > 0 and total_analyzed % 5 == 0:
        print(f"\n🏁 CHECKPOINT: {total_analyzed} guidelines analyzed!")
        print("   Consider reviewing progress and taking a break.")

    # Suggest next guideline
    if args.suggest_next and first_pending:
        print(f"\n{'=' * 70}")
        print("NEXT GUIDELINE TO ANALYZE:")
        print("=" * 70)
        print(f"\n  Guideline: {first_pending}")
        print(f"  Batch: {first_pending_batch}")
        print(f"\n  Run this command to see full context:")
        print(f"    uv run prepare-outlier-analysis --standard {standard} --guideline \"{first_pending}\" --batch {first_pending_batch}")
    elif total_analyzed == total_outliers:
        print(f"\n🎉 All outliers have been analyzed!")
        print(f"   Run: uv run generate-analysis-reports --standard {standard} --batches {','.join(map(str, batches))}")


if __name__ == "__main__":
    main()
