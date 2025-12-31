#!/usr/bin/env python3
"""
Generate or update verification progress tracking file.

This script assigns MISRA guidelines to batches based on:
- Current confidence level
- Applicability to Rust
- Similarity scores
- MISRA category

Batch Structure:
  1. High-score direct: existing high-confidence + direct with max score >= 0.65
  2. Not applicable: applicability_all_rust = not_applicable
  3. Stdlib & Resources: Categories 21+22, direct, not in batch 1
  4. Medium-score direct: remaining direct with score 0.5-0.65
  5. Edge cases: partial, rust_prevents, and any remaining
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


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


def get_misra_category(guideline_id: str) -> str:
    """Extract MISRA category from guideline ID."""
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

    # Build lookup for quick access
    guideline_data: dict[str, dict[str, Any]] = {}
    for m in mappings:
        gid = m["guideline_id"]
        guideline_data[gid] = {
            "confidence": m.get("confidence", "medium"),
            "applicability": m.get("applicability_all_rust", "unmapped"),
            "max_score": get_max_similarity_score(gid, similarity_results),
            "category": get_misra_category(gid),
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
    existing_progress: dict[str, Any] | None = None,
    preserve_completed: bool = False,
) -> dict[str, Any]:
    """Create the verification progress structure."""
    today = date.today().isoformat()

    # Track existing verified guidelines if preserving
    verified_guidelines: dict[str, dict[str, Any]] = {}
    existing_sessions: list[dict[str, Any]] = []

    if existing_progress and preserve_completed:
        for batch in existing_progress.get("batches", []):
            for g in batch.get("guidelines", []):
                if g.get("status") == "verified":
                    verified_guidelines[g["guideline_id"]] = {
                        "verified_date": g.get("verified_date"),
                        "session_id": g.get("session_id"),
                        "notes": g.get("notes", ""),
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
    total_verified = len(verified_guidelines)

    progress = {
        "standard": "misra_c_2025",
        "total_guidelines": total_guidelines,
        "verification_started": existing_progress.get("verification_started", today)
        if existing_progress
        else today,
        "last_updated": today,
        "summary": {
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
                        "verified_date": g_info["verified_date"],
                        "session_id": g_info["session_id"],
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

        # Determine batch status
        if batch_verified == len(guideline_ids) and len(guideline_ids) > 0:
            batch_status = "completed"
        elif batch_verified > 0:
            batch_status = "in_progress"
        else:
            batch_status = "pending"

        progress["batches"].append(
            {
                "batch_id": batch_id,
                "name": batch_def["name"],
                "description": batch_def["description"],
                "status": batch_status,
                "guidelines": guidelines,
                "started": None,  # Will be set when first guideline is verified
                "completed": None,
            }
        )

        progress["summary"]["by_batch"][str(batch_id)] = {
            "verified": batch_verified,
            "pending": batch_pending,
        }

    return progress


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
        "--output",
        type=Path,
        default=Path(__file__).parent.parent
        / "coding-standards-fls-mapping"
        / "verification_progress.json",
        help="Output path (default: ../coding-standards-fls-mapping/verification_progress.json)",
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

    args = parser.parse_args()

    # Load required data
    tools_dir = Path(__file__).parent
    mappings_path = (
        tools_dir.parent
        / "coding-standards-fls-mapping"
        / "mappings"
        / "misra_c_to_fls.json"
    )
    similarity_path = (
        tools_dir.parent / "embeddings" / "similarity" / "misra_c_to_fls.json"
    )

    if not mappings_path.exists():
        print(f"Error: Mappings file not found: {mappings_path}", file=sys.stderr)
        return 1

    if not similarity_path.exists():
        print(f"Error: Similarity file not found: {similarity_path}", file=sys.stderr)
        return 1

    print("Loading data...")
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
    progress = create_progress_file(batches, existing_progress, preserve)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, progress)

    print(f"\nSaved: {args.output}")
    print(f"  Total guidelines: {progress['total_guidelines']}")
    print(f"  Verified: {progress['summary']['total_verified']}")
    print(f"  Pending: {progress['summary']['total_pending']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
