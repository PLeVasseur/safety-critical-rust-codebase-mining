#!/usr/bin/env python3
"""
Generate or update verification progress tracking file.

This script assigns guidelines to batches based on:
- Current confidence level
- Applicability to Rust
- Similarity scores
- Guideline category

Batch Structure:
  1. High-score direct: existing high-confidence + direct with max score >= 0.65
  2. Not applicable: applicability_all_rust = not_applicable
  3. Stdlib & Resources: Categories 21+22, direct, not in batch 1
  4. Medium-score direct: remaining direct with score 0.5-0.65
  5. Edge cases: partial, rust_prevents, and any remaining

Usage:
    uv run scaffold-progress --standard misra-c
    uv run scaffold-progress --standard misra-c --force
    uv run scaffold-progress --standard misra-c --dry-run
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from fls_tools.shared import (
    get_project_root,
    get_standard_mappings_path,
    get_standard_similarity_path,
    get_verification_progress_path,
    normalize_standard,
    VALID_STANDARDS,
    get_guideline_schema_version,
)


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Save JSON file with consistent formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def get_max_similarity_score(
    guideline_id: str, similarity_results: dict[str, Any]
) -> float:
    """Get maximum similarity score for a guideline."""
    if guideline_id not in similarity_results.get("results", {}):
        return 0.0

    result = similarity_results["results"][guideline_id]
    top_matches = result.get("top_matches", [])

    if not top_matches:
        return 0.0

    return max(m.get("similarity", 0.0) for m in top_matches)


def get_guideline_category(guideline_id: str) -> str:
    """Extract category from guideline ID."""
    if guideline_id.startswith("Dir"):
        return "Directives"
    # Extract number from "Rule X.Y"
    parts = guideline_id.split()
    if len(parts) >= 2:
        return parts[1].split(".")[0]
    return "Unknown"


def assign_batches(
    mappings: list[dict[str, Any]], similarity_results: dict[str, Any]
) -> dict[int, list[str]]:
    """
    Assign guidelines to batches based on criteria.

    Returns dict mapping batch_id to list of guideline_ids.
    """
    batches: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: [], 5: []}
    assigned: set[str] = set()

    # Build lookup for quick access - handle both v1 and v2 formats
    guideline_data: dict[str, dict[str, Any]] = {}
    for m in mappings:
        gid = m["guideline_id"]
        schema_ver = get_guideline_schema_version(m)
        
        if schema_ver == "1.0":
            confidence = m.get("confidence", "medium")
            applicability = m.get("applicability_all_rust", "unmapped")
        else:
            # v2: Get from all_rust context
            all_rust = m.get("all_rust", {})
            confidence = all_rust.get("confidence", "medium")
            # Convert v2 applicability values to v1 for batch assignment
            app_v2 = all_rust.get("applicability", "no")
            applicability = {"yes": "direct", "partial": "partial", "no": "not_applicable"}.get(app_v2, "unmapped")
        
        guideline_data[gid] = {
            "confidence": confidence,
            "applicability": applicability,
            "max_score": get_max_similarity_score(gid, similarity_results),
            "category": get_guideline_category(gid),
        }

    # Batch 1: High-confidence OR (direct AND max_score >= 0.65)
    for gid, data in guideline_data.items():
        if data["confidence"] == "high":
            batches[1].append(gid)
            assigned.add(gid)
        elif data["applicability"] == "direct" and data["max_score"] >= 0.65:
            batches[1].append(gid)
            assigned.add(gid)

    # Batch 2: not_applicable (not already assigned)
    for gid, data in guideline_data.items():
        if gid in assigned:
            continue
        if data["applicability"] == "not_applicable":
            batches[2].append(gid)
            assigned.add(gid)

    # Batch 3: Categories 21+22, direct, not already assigned
    for gid, data in guideline_data.items():
        if gid in assigned:
            continue
        if data["category"] in ("21", "22") and data["applicability"] == "direct":
            batches[3].append(gid)
            assigned.add(gid)

    # Batch 4: Remaining direct with score 0.5-0.65
    for gid, data in guideline_data.items():
        if gid in assigned:
            continue
        if data["applicability"] == "direct" and 0.5 <= data["max_score"] < 0.65:
            batches[4].append(gid)
            assigned.add(gid)

    # Batch 5: Everything remaining
    for gid in guideline_data:
        if gid not in assigned:
            batches[5].append(gid)
            assigned.add(gid)

    # Sort each batch by guideline ID for consistency
    def sort_key(gid: str) -> tuple[int, int, int]:
        """Sort by type (Dir=0, Rule=1), then category, then number."""
        if gid.startswith("Dir"):
            parts = gid.split()
            nums = parts[1].split(".")
            return (0, int(nums[0]), int(nums[1]) if len(nums) > 1 else 0)
        else:
            parts = gid.split()
            nums = parts[1].split(".")
            return (1, int(nums[0]), int(nums[1]) if len(nums) > 1 else 0)

    for batch_id in batches:
        batches[batch_id].sort(key=sort_key)

    return batches


def create_progress_file(
    batches: dict[int, list[str]],
    standard: str,
    existing_progress: dict[str, Any] | None = None,
    preserve_completed: bool = False,
    schema_version: str = "1.0",
) -> dict[str, Any]:
    """Create the verification progress structure.
    
    Args:
        batches: Mapping of batch_id to list of guideline IDs
        standard: Standard name (e.g., 'misra-c')
        existing_progress: Existing progress data to preserve
        preserve_completed: Whether to preserve completed guidelines
        schema_version: "1.0" for flat, "2.0" for per-context
    """
    today = date.today().isoformat()

    # Track existing verified guidelines if preserving
    verified_guidelines: dict[str, dict[str, Any]] = {}
    existing_sessions: list[dict[str, Any]] = []

    if existing_progress and preserve_completed:
        existing_schema = existing_progress.get("schema_version", "1.0")
        for batch in existing_progress.get("batches", []):
            for g in batch.get("guidelines", []):
                gid = g["guideline_id"]
                if existing_schema == "1.0":
                    if g.get("status") == "verified":
                        verified_guidelines[gid] = {
                            "verified_date": g.get("verified_date"),
                            "session_id": g.get("session_id"),
                            "notes": g.get("notes", ""),
                        }
                else:
                    # v2: Check both contexts
                    all_rust = g.get("all_rust", {})
                    safe_rust = g.get("safe_rust", {})
                    if all_rust.get("verified") or safe_rust.get("verified"):
                        verified_guidelines[gid] = {
                            "all_rust": all_rust,
                            "safe_rust": safe_rust,
                        }
        existing_sessions = existing_progress.get("sessions", [])

    batch_definitions = [
        {
            "batch_id": 1,
            "name": "High-score direct mappings",
            "description": "Re-review existing high-confidence entries + direct mappings with similarity >= 0.65",
        },
        {
            "batch_id": 2,
            "name": "Not applicable",
            "description": "Guidelines not applicable to Rust - require FLS justification for why no equivalent exists",
        },
        {
            "batch_id": 3,
            "name": "Stdlib & Resources",
            "description": "Categories 21 (Standard library) and 22 (Resources) - remaining direct mappings",
        },
        {
            "batch_id": 4,
            "name": "Medium-score direct",
            "description": "Remaining direct mappings with similarity score 0.5-0.65",
        },
        {
            "batch_id": 5,
            "name": "Edge cases",
            "description": "Partial mappings, rust_prevents, and any remaining guidelines",
        },
    ]

    total_guidelines = sum(len(g) for g in batches.values())

    # Use internal standard name (snake_case) for the field
    internal_standard = normalize_standard(standard)

    if schema_version == "1.0":
        # v1: Flat structure
        total_verified = len(verified_guidelines)
        
        progress = {
            "schema_version": "1.0",
            "standard": internal_standard,
            "total_guidelines": total_guidelines,
            "verification_started": existing_progress.get("verification_started", today)
            if existing_progress
            else today,
            "last_updated": today,
            "summary": {
                "total_guidelines": total_guidelines,
                "total_verified": total_verified,
                "total_pending": total_guidelines - total_verified,
                "by_batch": {},
            },
            "batches": [],
            "sessions": existing_sessions,
        }

        for batch_def in batch_definitions:
            batch_id = batch_def["batch_id"]
            guideline_ids = batches.get(batch_id, [])

            guidelines = []
            batch_verified = 0
            for gid in guideline_ids:
                if gid in verified_guidelines:
                    g_info = verified_guidelines[gid]
                    guidelines.append(
                        {
                            "guideline_id": gid,
                            "status": "verified",
                            "verified_date": g_info.get("verified_date"),
                            "session_id": g_info.get("session_id"),
                            "verified": True,
                            "notes": g_info.get("notes", ""),
                        }
                    )
                    batch_verified += 1
                else:
                    guidelines.append(
                        {
                            "guideline_id": gid,
                            "status": "pending",
                            "verified_date": None,
                            "session_id": None,
                        }
                    )

            batch_pending = len(guideline_ids) - batch_verified
            batch_status = _determine_batch_status(batch_verified, len(guideline_ids))

            progress["batches"].append(
                {
                    "batch_id": batch_id,
                    "name": batch_def["name"],
                    "description": batch_def["description"],
                    "status": batch_status,
                    "guidelines": guidelines,
                    "started": None,
                    "completed": None,
                }
            )

            progress["summary"]["by_batch"][str(batch_id)] = {
                "verified": batch_verified,
                "pending": batch_pending,
            }

    else:
        # v2: Per-context structure
        all_rust_verified = 0
        safe_rust_verified = 0
        both_verified = 0
        
        for gid in verified_guidelines:
            v_info = verified_guidelines[gid]
            all_v = v_info.get("all_rust", {}).get("verified", False)
            safe_v = v_info.get("safe_rust", {}).get("verified", False)
            if all_v:
                all_rust_verified += 1
            if safe_v:
                safe_rust_verified += 1
            if all_v and safe_v:
                both_verified += 1

        progress = {
            "schema_version": "2.0",
            "standard": internal_standard,
            "total_guidelines": total_guidelines,
            "verification_started": existing_progress.get("verification_started", today)
            if existing_progress
            else today,
            "last_updated": today,
            "summary": {
                "total_guidelines": total_guidelines,
                "all_rust_verified": all_rust_verified,
                "safe_rust_verified": safe_rust_verified,
                "both_verified": both_verified,
                "pending": total_guidelines - both_verified,
                "by_batch": {},
            },
            "batches": [],
            "sessions": existing_sessions,
        }

        for batch_def in batch_definitions:
            batch_id = batch_def["batch_id"]
            guideline_ids = batches.get(batch_id, [])

            guidelines = []
            batch_all_rust = 0
            batch_safe_rust = 0
            batch_both = 0
            
            for gid in guideline_ids:
                if gid in verified_guidelines:
                    v_info = verified_guidelines[gid]
                    all_rust_ctx = v_info.get("all_rust", {"verified": False})
                    safe_rust_ctx = v_info.get("safe_rust", {"verified": False})
                    
                    if all_rust_ctx.get("verified"):
                        batch_all_rust += 1
                    if safe_rust_ctx.get("verified"):
                        batch_safe_rust += 1
                    if all_rust_ctx.get("verified") and safe_rust_ctx.get("verified"):
                        batch_both += 1
                    
                    guidelines.append({
                        "guideline_id": gid,
                        "all_rust": all_rust_ctx,
                        "safe_rust": safe_rust_ctx,
                    })
                else:
                    guidelines.append({
                        "guideline_id": gid,
                        "all_rust": {"verified": False, "verified_date": None, "verified_by_session": None},
                        "safe_rust": {"verified": False, "verified_date": None, "verified_by_session": None},
                    })

            batch_pending = len(guideline_ids) - batch_both
            batch_status = _determine_batch_status(batch_both, len(guideline_ids))

            progress["batches"].append(
                {
                    "batch_id": batch_id,
                    "name": batch_def["name"],
                    "description": batch_def["description"],
                    "status": batch_status,
                    "guidelines": guidelines,
                    "started": None,
                    "completed": None,
                }
            )

            progress["summary"]["by_batch"][str(batch_id)] = {
                "all_rust_verified": batch_all_rust,
                "safe_rust_verified": batch_safe_rust,
                "both_verified": batch_both,
                "pending": batch_pending,
            }

    return progress


def _determine_batch_status(verified_count: int, total_count: int) -> str:
    """Determine batch status based on verification count."""
    if verified_count == total_count and total_count > 0:
        return "completed"
    elif verified_count > 0:
        return "in_progress"
    else:
        return "pending"


def print_dry_run(batches: dict[int, list[str]], mappings: list[dict], similarity_results: dict) -> None:
    """Print batch assignments without writing file."""
    batch_names = {
        1: "High-score direct mappings",
        2: "Not applicable",
        3: "Stdlib & Resources (Categories 21+22)",
        4: "Medium-score direct",
        5: "Edge cases",
    }

    # Build lookup for applicability
    app_lookup = {m["guideline_id"]: m.get("applicability_all_rust", "unmapped") for m in mappings}
    conf_lookup = {m["guideline_id"]: m.get("confidence", "medium") for m in mappings}

    print("=" * 60)
    print("BATCH ASSIGNMENT PREVIEW")
    print("=" * 60)
    print()

    total = 0
    for batch_id in sorted(batches.keys()):
        guidelines = batches[batch_id]
        total += len(guidelines)

        print(f"Batch {batch_id}: {batch_names[batch_id]}")
        print(f"  {len(guidelines)} guidelines")

        # Show breakdown
        if guidelines:
            high_conf = sum(1 for g in guidelines if conf_lookup.get(g) == "high")
            if high_conf > 0:
                print(f"    - {high_conf} existing high-confidence (re-review)")

            by_app = {}
            for g in guidelines:
                app = app_lookup.get(g, "unmapped")
                by_app[app] = by_app.get(app, 0) + 1
            for app, count in sorted(by_app.items()):
                if app != "high":  # Already counted
                    print(f"    - {count} {app}")

            # Show first few
            preview = guidelines[:8]
            suffix = f", ... (+{len(guidelines) - 8} more)" if len(guidelines) > 8 else ""
            print(f"  Guidelines: {', '.join(preview)}{suffix}")

        print()

    print("=" * 60)
    print(f"Total: {total} guidelines across {len(batches)} batches")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or update verification progress tracking file."
    )
    parser.add_argument(
        "--standard", "-s",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c, misra-cpp, cert-c, cert-cpp)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: coding-standards-fls-mapping/verification/{standard}/progress.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file completely, regenerating all batches",
    )
    parser.add_argument(
        "--preserve-completed",
        action="store_true",
        help="Keep verified guidelines when regenerating (default if file exists without --force)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print batch assignments without writing file",
    )
    parser.add_argument(
        "--schema-version",
        type=str,
        choices=["1.0", "2.0"],
        default="2.0",
        help="Schema version to generate (default: 2.0 for per-context)",
    )

    args = parser.parse_args()

    root = get_project_root()
    standard = args.standard

    # Set default output path if not specified
    if args.output is None:
        args.output = get_verification_progress_path(root, standard)

    # Load required data
    mappings_path = get_standard_mappings_path(root, standard)
    similarity_path = get_standard_similarity_path(root, standard)

    if not mappings_path.exists():
        print(f"Error: Mappings file not found: {mappings_path}", file=sys.stderr)
        return 1

    if not similarity_path.exists():
        print(f"Error: Similarity file not found: {similarity_path}", file=sys.stderr)
        return 1

    print(f"Loading data for {standard}...")
    mappings_data = load_json(mappings_path)
    similarity_results = load_json(similarity_path)

    mappings = mappings_data.get("mappings", [])
    print(f"  Loaded {len(mappings)} guidelines from mappings")
    print(
        f"  Loaded similarity results for {len(similarity_results.get('results', {}))} guidelines"
    )

    # Assign batches
    print("\nAssigning guidelines to batches...")
    batches = assign_batches(mappings, similarity_results)

    for batch_id, guidelines in batches.items():
        print(f"  Batch {batch_id}: {len(guidelines)} guidelines")

    # Dry run - just print
    if args.dry_run:
        print()
        print_dry_run(batches, mappings, similarity_results)
        return 0

    # Check if output exists
    existing_progress = None
    if args.output.exists():
        if not args.force and not args.preserve_completed:
            print(
                f"\nError: Output file already exists: {args.output}",
                file=sys.stderr,
            )
            print(
                "Use --force to overwrite or --preserve-completed to keep verified entries",
                file=sys.stderr,
            )
            return 1

        existing_progress = load_json(args.output)
        verified_count = existing_progress.get("summary", {}).get("total_verified", 0)

        if args.force and verified_count > 0:
            print(f"\nWarning: Overwriting file with {verified_count} verified entries")
        elif args.preserve_completed:
            print(f"\nPreserving {verified_count} verified entries")

    # Create progress file
    preserve = args.preserve_completed or (
        existing_progress is not None and not args.force
    )
    progress = create_progress_file(
        batches, standard, existing_progress, preserve, args.schema_version
    )

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, progress)

    print(f"\nSaved: {args.output}")
    print(f"  Total guidelines: {progress['total_guidelines']}")
    
    if args.schema_version == "2.0":
        summary = progress['summary']
        print(f"  all_rust verified:  {summary['all_rust_verified']}")
        print(f"  safe_rust verified: {summary['safe_rust_verified']}")
        print(f"  Both verified:      {summary['both_verified']}")
        print(f"  Pending:            {summary['pending']}")
    else:
        print(f"  Verified: {progress['summary']['total_verified']}")
        print(f"  Pending: {progress['summary']['total_pending']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
