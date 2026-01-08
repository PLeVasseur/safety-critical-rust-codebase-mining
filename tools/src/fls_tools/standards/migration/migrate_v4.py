#!/usr/bin/env python3
"""
migrate-to-v4 - Migrate mapping entries to vX.2 with paragraph coverage fields.

This tool adds paragraph coverage tracking to existing mapping entries:
- v1.0/v1.1 → v1.2 (flat structure + paragraph fields)
- v2.0/v2.1 → v2.2 (per-context structure + paragraph fields per context)
- v3.0/v3.1 → v3.2 (per-context structure + paragraph fields per context)

Entries without paragraph-level matches get a migration waiver explaining they
need re-verification.

Usage:
    # Preview migration
    uv run migrate-to-v4 --standard misra-c --dry-run
    
    # Execute migration
    uv run migrate-to-v4 --standard misra-c --apply
    
    # Generate report only
    uv run migrate-to-v4 --standard misra-c --report
"""

import argparse
import json
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_standard_mappings_path,
    VALID_STANDARDS,
    detect_schema_version,
    is_v1_family,
    count_matches_by_category,
    count_context_matches,
    build_migration_waiver,
)


def get_new_version(current_version: str) -> str | None:
    """
    Determine the new version for migration.
    
    Returns None if version is already vX.2 or v4.0 (no migration needed).
    """
    if current_version in ("1.0", "1.1"):
        return "1.2"
    elif current_version in ("2.0", "2.1"):
        return "2.2"
    elif current_version in ("3.0", "3.1"):
        return "3.2"
    elif current_version in ("1.2", "2.2", "3.2", "4.0"):
        return None  # Already migrated
    else:
        return None  # Unknown version


def migrate_v1_entry(entry: dict, migration_date: str) -> dict:
    """
    Migrate a v1.x entry to v1.2.
    
    v1 entries have flat structure with accepted_matches at entry level.
    """
    entry = deepcopy(entry)
    old_version = entry.get("schema_version", "1.0")
    
    # Get new version
    new_version = get_new_version(old_version)
    if new_version is None:
        return entry
    
    # Count matches
    matches = entry.get("accepted_matches", [])
    para_count, section_count = count_matches_by_category(matches)
    
    # Update entry
    entry["schema_version"] = new_version
    entry["paragraph_match_count"] = para_count
    entry["section_match_count"] = section_count
    
    # Add waiver if no paragraph matches
    if para_count == 0:
        entry["paragraph_level_waiver"] = build_migration_waiver(
            old_version, migration_date, para_count, section_count
        )
    else:
        entry["paragraph_level_waiver"] = None
    
    return entry


def migrate_v2_entry(entry: dict, migration_date: str) -> dict:
    """
    Migrate a v2.x or v3.x entry to vX.2.
    
    v2+ entries have per-context structure with accepted_matches in each context.
    """
    entry = deepcopy(entry)
    old_version = entry.get("schema_version", "2.0")
    
    # Get new version
    new_version = get_new_version(old_version)
    if new_version is None:
        return entry
    
    entry["schema_version"] = new_version
    
    # Process each context
    for ctx in ["all_rust", "safe_rust"]:
        ctx_data = entry.get(ctx)
        if not ctx_data:
            continue
        
        # Count matches for this context
        matches = ctx_data.get("accepted_matches", [])
        para_count, section_count = count_matches_by_category(matches)
        
        # Add paragraph fields
        ctx_data["paragraph_match_count"] = para_count
        ctx_data["section_match_count"] = section_count
        
        # Add waiver if no paragraph matches
        if para_count == 0:
            ctx_data["paragraph_level_waiver"] = build_migration_waiver(
                old_version, migration_date, para_count, section_count
            )
        else:
            ctx_data["paragraph_level_waiver"] = None
    
    return entry


def migrate_entry(entry: dict, migration_date: str) -> dict:
    """Migrate a single mapping entry to vX.2."""
    version = detect_schema_version(entry)
    
    if is_v1_family(entry):
        return migrate_v1_entry(entry, migration_date)
    else:
        return migrate_v2_entry(entry, migration_date)


def compute_stats(entries: list[dict]) -> dict:
    """
    Compute migration statistics.
    
    Returns dict with:
    - version_counts: count by version before migration
    - paragraph_stats: has_paragraphs, section_only, no_matches
    - per_context_stats: for v2+ entries
    - needs_reverification: list of guideline_ids
    """
    stats = {
        "total": len(entries),
        "version_counts": {},
        "paragraph_stats": {
            "has_paragraphs": 0,
            "section_only": 0,
            "no_matches": 0,
        },
        "per_context_stats": {
            "all_rust": {"has_paragraphs": 0, "section_only": 0, "no_matches": 0},
            "safe_rust": {"has_paragraphs": 0, "section_only": 0, "no_matches": 0},
        },
        "needs_reverification": [],
        "no_matches_entries": [],
    }
    
    for entry in entries:
        gid = entry.get("guideline_id", "UNKNOWN")
        version = detect_schema_version(entry)
        
        # Count versions
        stats["version_counts"][version] = stats["version_counts"].get(version, 0) + 1
        
        # Check paragraph coverage
        if is_v1_family(entry):
            # v1 flat structure
            matches = entry.get("accepted_matches", [])
            para_count, section_count = count_matches_by_category(matches)
            
            if para_count > 0:
                stats["paragraph_stats"]["has_paragraphs"] += 1
            elif section_count > 0:
                stats["paragraph_stats"]["section_only"] += 1
                stats["needs_reverification"].append(gid)
            else:
                stats["paragraph_stats"]["no_matches"] += 1
                stats["no_matches_entries"].append(gid)
        else:
            # v2+ per-context structure
            entry_has_para = False
            entry_has_section = False
            entry_has_any = False
            
            for ctx in ["all_rust", "safe_rust"]:
                ctx_data = entry.get(ctx, {})
                if not ctx_data:
                    continue
                
                matches = ctx_data.get("accepted_matches", [])
                para_count, section_count = count_matches_by_category(matches)
                
                if para_count > 0:
                    stats["per_context_stats"][ctx]["has_paragraphs"] += 1
                    entry_has_para = True
                    entry_has_any = True
                elif section_count > 0:
                    stats["per_context_stats"][ctx]["section_only"] += 1
                    entry_has_section = True
                    entry_has_any = True
                else:
                    stats["per_context_stats"][ctx]["no_matches"] += 1
            
            # Entry-level classification
            if entry_has_para:
                stats["paragraph_stats"]["has_paragraphs"] += 1
            elif entry_has_section:
                stats["paragraph_stats"]["section_only"] += 1
                stats["needs_reverification"].append(gid)
            elif not entry_has_any:
                stats["paragraph_stats"]["no_matches"] += 1
                stats["no_matches_entries"].append(gid)
    
    return stats


def generate_report(
    stats_before: dict,
    stats_after: dict,
    migration_date: str,
    standard: str,
) -> str:
    """Generate a Markdown migration report."""
    lines = [
        f"# v4 Migration Report: {standard}",
        "",
        f"**Date:** {migration_date}",
        f"**Total entries:** {stats_before['total']}",
        "",
        "## Summary",
        "",
        "| Category | Count | Percentage |",
        "|----------|-------|------------|",
    ]
    
    total = stats_before["total"]
    for key, label in [
        ("has_paragraphs", "Has paragraph matches (OK)"),
        ("section_only", "Section-only (needs re-verification)"),
        ("no_matches", "No matches (needs re-verification)"),
    ]:
        count = stats_before["paragraph_stats"][key]
        pct = (count / total * 100) if total > 0 else 0
        lines.append(f"| {label} | {count} | {pct:.1f}% |")
    
    lines.extend([
        "",
        "## Version Distribution",
        "",
        "### Before Migration",
        "",
        "| Version | Count |",
        "|---------|-------|",
    ])
    
    for version, count in sorted(stats_before["version_counts"].items()):
        lines.append(f"| v{version} | {count} |")
    
    lines.extend([
        "",
        "### After Migration",
        "",
        "| Version | Count |",
        "|---------|-------|",
    ])
    
    for version, count in sorted(stats_after["version_counts"].items()):
        lines.append(f"| v{version} | {count} |")
    
    # Per-context summary for v2+ entries
    lines.extend([
        "",
        "## Per-Context Summary (v2+ entries)",
        "",
        "| Context | Has Paragraphs | Section-Only | No Matches |",
        "|---------|----------------|--------------|------------|",
    ])
    
    for ctx in ["all_rust", "safe_rust"]:
        ctx_stats = stats_before["per_context_stats"][ctx]
        lines.append(
            f"| {ctx} | {ctx_stats['has_paragraphs']} | "
            f"{ctx_stats['section_only']} | {ctx_stats['no_matches']} |"
        )
    
    # Entries needing re-verification
    if stats_before["needs_reverification"]:
        lines.extend([
            "",
            "## Entries Requiring Re-verification",
            "",
            "These entries have only section-level matches and need paragraph-level content added:",
            "",
        ])
        for gid in sorted(stats_before["needs_reverification"]):
            lines.append(f"- {gid}")
    
    # Entries with no matches
    if stats_before["no_matches_entries"]:
        lines.extend([
            "",
            "## Entries With No Matches",
            "",
            "These entries have no FLS matches (likely `no_equivalent` rationale):",
            "",
        ])
        for gid in sorted(stats_before["no_matches_entries"]):
            lines.append(f"- {gid}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate mapping entries to vX.2 with paragraph coverage fields"
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
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration and write to file"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate report only (no changes)"
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default=None,
        help="Path to write Markdown report (default: print to stdout)"
    )
    args = parser.parse_args()
    
    # Validate arguments
    if not any([args.dry_run, args.apply, args.report]):
        print("ERROR: Must specify --dry-run, --apply, or --report", file=sys.stderr)
        sys.exit(1)
    
    if args.apply and args.dry_run:
        print("ERROR: Cannot use both --apply and --dry-run", file=sys.stderr)
        sys.exit(1)
    
    root = get_project_root()
    migration_date = date.today().isoformat()
    
    # Load mapping file
    mapping_path = get_standard_mappings_path(root, args.standard)
    if not mapping_path.exists():
        print(f"ERROR: Mapping file not found: {mapping_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading mappings from {mapping_path}", file=sys.stderr)
    with open(mapping_path) as f:
        mappings = json.load(f)
    
    entries = mappings.get("mappings", [])
    print(f"Found {len(entries)} mapping entries", file=sys.stderr)
    
    # Compute stats before migration
    stats_before = compute_stats(entries)
    
    # Migrate entries
    migrated_entries = []
    migration_counts = {
        "1.0→1.2": 0,
        "1.1→1.2": 0,
        "2.0→2.2": 0,
        "2.1→2.2": 0,
        "3.0→3.2": 0,
        "3.1→3.2": 0,
        "unchanged": 0,
    }
    
    for entry in entries:
        old_version = detect_schema_version(entry)
        migrated = migrate_entry(entry, migration_date)
        new_version = detect_schema_version(migrated)
        migrated_entries.append(migrated)
        
        if old_version != new_version:
            key = f"{old_version}→{new_version}"
            migration_counts[key] = migration_counts.get(key, 0) + 1
        else:
            migration_counts["unchanged"] += 1
    
    # Compute stats after migration
    stats_after = compute_stats(migrated_entries)
    
    # Generate report
    report = generate_report(stats_before, stats_after, migration_date, args.standard)
    
    # Print migration summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Migration Summary for {args.standard}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    
    for key, count in sorted(migration_counts.items()):
        if count > 0:
            print(f"  {key}: {count}", file=sys.stderr)
    
    print(f"\nParagraph coverage:", file=sys.stderr)
    for key, count in stats_before["paragraph_stats"].items():
        print(f"  {key}: {count}", file=sys.stderr)
    
    # Handle output
    if args.report or args.dry_run:
        if args.output_report:
            with open(args.output_report, "w") as f:
                f.write(report)
            print(f"\nReport written to {args.output_report}", file=sys.stderr)
        else:
            print("\n" + report)
    
    if args.dry_run:
        print("\n[DRY RUN] No files were modified.", file=sys.stderr)
        return
    
    if args.apply:
        # Create backup
        backup_path = mapping_path.with_suffix(f".json.backup.{migration_date}")
        with open(backup_path, "w") as f:
            json.dump(mappings, f, indent=2)
        print(f"\nBackup created: {backup_path}", file=sys.stderr)
        
        # Write migrated mappings
        mappings["mappings"] = migrated_entries
        with open(mapping_path, "w") as f:
            json.dump(mappings, f, indent=2)
            f.write("\n")
        print(f"Migration applied to {mapping_path}", file=sys.stderr)
        
        # Write report
        if args.output_report:
            with open(args.output_report, "w") as f:
                f.write(report)
            print(f"Report written to {args.output_report}", file=sys.stderr)
        
        print("\nDone. Run validate-standards to verify migration.", file=sys.stderr)


if __name__ == "__main__":
    main()
