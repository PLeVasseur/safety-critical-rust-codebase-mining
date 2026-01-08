#!/usr/bin/env python3
"""
record-investigation - Record LLM investigation findings to an outlier analysis file.

This tool is called by the OpenCode LLM during interactive review when a user
requests investigation. It records structured findings to the outlier file's
`llm_investigation` section.

Usage:
    uv run record-investigation \\
        --standard misra-c \\
        --guideline "Dir 4.3" \\
        --aspect fls_removal \\
        --fls-id fls_3fg60jblx0xb \\
        --context all_rust \\
        --source "embeddings/fls/chapter_22.json" \\
        --fls-content "Inline assembly is written as..." \\
        --relevance "Directly addresses MISRA's encapsulation requirement" \\
        --recommendation "KEEP" \\
        --confidence high
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
)


VALID_ASPECTS = [
    "fls_removal",
    "fls_addition", 
    "categorization",
    "specificity",
    "add6_divergence",
    "all",
]

VALID_CONFIDENCE = ["high", "medium", "low"]


def create_investigation_entry(
    aspect: str,
    fls_id: str | None,
    context: str | None,
    sources: list[str],
    fls_content: str | None,
    relevance: str,
    recommendation: str,
    confidence: str,
    user_guidance: str | None,
    notes: str | None,
) -> dict:
    """Create a structured investigation entry."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "aspect": aspect,
        "target": {},
        "trigger": "human_request",
        "sources_consulted": sources,
        "findings": {
            "relevance_assessment": relevance,
            "recommendation": recommendation,
            "confidence": confidence,
        },
    }
    
    # Add target details
    if fls_id:
        entry["target"]["fls_id"] = fls_id
    if context:
        entry["target"]["context"] = context
    
    # Add optional fields
    if fls_content:
        entry["findings"]["fls_content_summary"] = fls_content
    if user_guidance:
        entry["user_guidance"] = user_guidance
    if notes:
        entry["findings"]["notes"] = notes
    
    return entry


def main():
    parser = argparse.ArgumentParser(
        description="Record LLM investigation findings to an outlier analysis file."
    )
    
    # Required parameters
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    parser.add_argument(
        "--guideline",
        required=True,
        help="Guideline ID (e.g., 'Dir 4.3', 'Rule 10.1')",
    )
    parser.add_argument(
        "--aspect",
        required=True,
        choices=VALID_ASPECTS,
        help="Aspect type being investigated",
    )
    parser.add_argument(
        "--relevance",
        required=True,
        help="Assessment of relevance to MISRA concern",
    )
    parser.add_argument(
        "--recommendation",
        required=True,
        help="Recommended action (e.g., KEEP, REMOVE, ACCEPT)",
    )
    parser.add_argument(
        "--confidence",
        required=True,
        choices=VALID_CONFIDENCE,
        help="Confidence level of the recommendation",
    )
    
    # Optional parameters
    parser.add_argument(
        "--fls-id",
        help="FLS ID (for FLS-specific aspects)",
    )
    parser.add_argument(
        "--context",
        choices=["all_rust", "safe_rust"],
        help="Context (all_rust or safe_rust)",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        dest="sources",
        help="Source file consulted (can be repeated)",
    )
    parser.add_argument(
        "--fls-content",
        help="Summary of FLS content examined",
    )
    parser.add_argument(
        "--user-guidance",
        help="User's guidance that informed investigation",
    )
    parser.add_argument(
        "--notes",
        help="Additional notes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be recorded without saving",
    )
    
    args = parser.parse_args()
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    # Load existing outlier analysis
    analysis = load_outlier_analysis(args.guideline, root)
    if not analysis:
        print(f"ERROR: No outlier analysis found for {args.guideline}", file=sys.stderr)
        print(f"  Expected location: {get_outlier_analysis_dir(root)}", file=sys.stderr)
        sys.exit(1)
    
    # Create investigation entry
    entry = create_investigation_entry(
        aspect=args.aspect,
        fls_id=args.fls_id,
        context=args.context,
        sources=args.sources,
        fls_content=args.fls_content,
        relevance=args.relevance,
        recommendation=args.recommendation,
        confidence=args.confidence,
        user_guidance=args.user_guidance,
        notes=args.notes,
    )
    
    # Initialize llm_investigation section if needed
    if "llm_investigation" not in analysis:
        analysis["llm_investigation"] = {"investigations": []}
    if "investigations" not in analysis["llm_investigation"]:
        analysis["llm_investigation"]["investigations"] = []
    
    # Add the new investigation
    analysis["llm_investigation"]["investigations"].append(entry)
    
    if args.dry_run:
        import json
        print("[DRY RUN] Would record investigation:")
        print(json.dumps(entry, indent=2))
        return
    
    # Save updated analysis
    save_outlier_analysis(args.guideline, analysis, root)
    
    print(f"Recorded investigation for {args.guideline}")
    print(f"  Aspect: {args.aspect}")
    if args.fls_id:
        print(f"  FLS ID: {args.fls_id}")
    if args.context:
        print(f"  Context: {args.context}")
    print(f"  Recommendation: {args.recommendation} (confidence: {args.confidence})")
    print(f"  Sources: {len(args.sources)} file(s)")


if __name__ == "__main__":
    main()
