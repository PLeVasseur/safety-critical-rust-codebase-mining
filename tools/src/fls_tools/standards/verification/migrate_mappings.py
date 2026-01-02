#!/usr/bin/env python3
"""
migrate-mappings - Enrich mapping entries with MISRA ADD-6 data.

Upgrades mapping entries by adding misra_add6 block:
  v1.0 → v1.1 (flat structure + ADD-6)
  v2.0 → v2.1 (per-context structure + ADD-6)

The version number indicates whether the entry was enriched via migration (v1.1/v2.1)
or created fresh during verification (v3.0).

Usage:
    uv run migrate-mappings --standard misra-c --dry-run
    uv run migrate-mappings --standard misra-c
"""

import argparse
import json
import sys
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_standard_mappings_path,
    get_misra_rust_applicability_path,
    get_guideline_schema_version,
    build_misra_add6_block,
    VALID_STANDARDS,
)


def migrate_entry(entry: dict, add6_all: dict) -> tuple[dict, str, str]:
    """
    Migrate a single mapping entry by adding ADD-6 data.
    
    Args:
        entry: The mapping entry to migrate
        add6_all: Dict of guideline_id -> ADD-6 data
    
    Returns:
        Tuple of (migrated_entry, old_version, new_version)
    """
    gid = entry.get("guideline_id", "")
    old_version = get_guideline_schema_version(entry)
    
    # Already enriched or v3?
    if old_version in ("1.1", "2.1", "3.0"):
        return entry, old_version, old_version
    
    # Get ADD-6 data
    add6 = add6_all.get(gid)
    if not add6:
        # No ADD-6 data available - cannot migrate
        return entry, old_version, old_version
    
    # Add misra_add6 block
    entry["misra_add6"] = build_misra_add6_block(add6)
    
    # Update schema version
    if old_version == "1.0":
        entry["schema_version"] = "1.1"
        return entry, "1.0", "1.1"
    elif old_version == "2.0":
        entry["schema_version"] = "2.1"
        return entry, "2.0", "2.1"
    
    return entry, old_version, old_version


def main():
    parser = argparse.ArgumentParser(
        description="Enrich mapping entries with MISRA ADD-6 data"
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard to migrate"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to file"
    )
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Load ADD-6 data
    add6_path = get_misra_rust_applicability_path(root)
    if not add6_path.exists():
        print(f"ERROR: ADD-6 data not found: {add6_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading ADD-6 data from {add6_path}", file=sys.stderr)
    with open(add6_path) as f:
        add6_data = json.load(f)
    add6_all = add6_data.get("guidelines", {})
    print(f"  Found {len(add6_all)} guidelines in ADD-6 data", file=sys.stderr)
    
    # Load mapping file
    mapping_path = get_standard_mappings_path(root, args.standard)
    if not mapping_path.exists():
        print(f"ERROR: Mapping file not found: {mapping_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading mappings from {mapping_path}", file=sys.stderr)
    with open(mapping_path) as f:
        mappings = json.load(f)
    
    # Track statistics
    stats = {
        "v1.0→v1.1": 0,
        "v2.0→v2.1": 0,
        "already_enriched": 0,
        "no_add6_data": 0,
    }
    no_add6_guidelines = []
    
    # Migrate each entry
    mapping_list = mappings.get("mappings", [])
    print(f"  Found {len(mapping_list)} mapping entries", file=sys.stderr)
    
    for i, entry in enumerate(mapping_list):
        gid = entry.get("guideline_id", f"unknown_{i}")
        old_version = get_guideline_schema_version(entry)
        
        migrated, old_v, new_v = migrate_entry(entry, add6_all)
        mapping_list[i] = migrated
        
        if old_v == new_v:
            if old_v in ("1.1", "2.1", "3.0"):
                stats["already_enriched"] += 1
            else:
                # Still v1.0 or v2.0 - means no ADD-6 data
                stats["no_add6_data"] += 1
                no_add6_guidelines.append(gid)
        elif old_v == "1.0" and new_v == "1.1":
            stats["v1.0→v1.1"] += 1
        elif old_v == "2.0" and new_v == "2.1":
            stats["v2.0→v2.1"] += 1
    
    # Report results
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Migration Summary for {args.standard}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  v1.0 → v1.1: {stats['v1.0→v1.1']}", file=sys.stderr)
    print(f"  v2.0 → v2.1: {stats['v2.0→v2.1']}", file=sys.stderr)
    print(f"  Already enriched (skipped): {stats['already_enriched']}", file=sys.stderr)
    print(f"  Missing ADD-6 data (skipped): {stats['no_add6_data']}", file=sys.stderr)
    
    if no_add6_guidelines:
        print(f"\nGuidelines without ADD-6 data:", file=sys.stderr)
        for gid in no_add6_guidelines[:10]:
            print(f"    - {gid}", file=sys.stderr)
        if len(no_add6_guidelines) > 10:
            print(f"    ... and {len(no_add6_guidelines) - 10} more", file=sys.stderr)
    
    total_migrated = stats["v1.0→v1.1"] + stats["v2.0→v2.1"]
    
    if args.dry_run:
        print(f"\nDRY RUN - no changes written", file=sys.stderr)
        print(f"Would migrate {total_migrated} entries", file=sys.stderr)
    else:
        if total_migrated > 0:
            with open(mapping_path, "w") as f:
                json.dump(mappings, f, indent=2)
            print(f"\nWrote changes to {mapping_path}", file=sys.stderr)
            print(f"Migrated {total_migrated} entries", file=sys.stderr)
        else:
            print(f"\nNo entries to migrate", file=sys.stderr)


if __name__ == "__main__":
    main()
