#!/usr/bin/env python3
"""
verify_batch.py - Phase 1: Data Gathering for FLS Verification

This script extracts all relevant data for a batch of guidelines:
- MISRA ADD-6 data for each guideline
- Similarity matches (section and paragraph) above thresholds
- Rationale from extracted text
- Wide-shot FLS content (matched sections + siblings + all rubrics)
- Current mapping state

Supports schema versions:
- v1.0: Flat verification_decision structure (legacy, read-only)
- v2.0: Per-context verification_decision (legacy, read-only)
- v3.0/v3.1/v3.2: Per-context + ADD-6 data (legacy)
- v4.0: Per-context + ADD-6 + enforced paragraph coverage (default for new batch reports)

Two output modes:
- LLM mode: Full JSON optimized for LLM consumption
- Human mode: Markdown report with JSON snippets for quick review

Usage:
    # Generate v4.0 batch report (default)
    uv run verify-batch --standard misra-c --batch 3 --session 1 --mode llm
    
    # Human-readable report
    uv run verify-batch --standard misra-c --batch 3 --mode human
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import jsonschema

from fls_tools.shared import (
    get_project_root,
    get_fls_dir,
    get_fls_index_path,
    get_fls_chapter_path,
    get_fls_section_mapping_path,
    get_standard_mappings_path,
    get_standard_similarity_path,
    get_standard_extracted_text_path,
    get_verification_progress_path,
    get_coding_standards_dir,
    get_batch_report_path,
    get_misra_rust_applicability_path,
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
    normalize_standard,
    VALID_STANDARDS,
    CATEGORY_NAMES,
    DEFAULT_SECTION_THRESHOLD,
    DEFAULT_PARAGRAPH_THRESHOLD,
    SchemaVersion,
    get_guideline_schema_version,
    build_misra_add6_block,
)


def load_json(path: Path, description: str) -> dict:
    """Load a JSON file with error handling."""
    if not path.exists():
        print(f"ERROR: {description} not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_batch_report_schema(root: Path) -> dict | None:
    """Load the batch report JSON schema."""
    schema_path = get_coding_standards_dir(root) / "schema" / "batch_report.schema.json"
    if not schema_path.exists():
        print(f"WARNING: Batch report schema not found: {schema_path}", file=sys.stderr)
        return None
    with open(schema_path) as f:
        return json.load(f)


def validate_batch_report(report: dict, schema: dict | None) -> list[str]:
    """
    Validate a batch report against the schema.
    
    Returns a list of validation errors (empty if valid).
    """
    if schema is None:
        return []
    
    errors = []
    try:
        jsonschema.validate(instance=report, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation error: {e.message}")
        if e.path:
            errors.append(f"  Path: {'.'.join(str(p) for p in e.path)}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema error: {e.message}")
    
    return errors


def load_add6_data(root: Path) -> dict:
    """Load MISRA ADD-6 Rust applicability data."""
    add6_path = get_misra_rust_applicability_path(root)
    if not add6_path.exists():
        print(f"WARNING: ADD-6 data not found: {add6_path}", file=sys.stderr)
        return {}
    with open(add6_path) as f:
        data = json.load(f)
    return data.get("guidelines", {})


def load_all_data(root: Path, standard: str) -> dict:
    """Load all required data sources for a standard."""
    data = {}
    
    # Required files - fail if missing
    data["mappings"] = load_json(
        get_standard_mappings_path(root, standard),
        f"{standard} to FLS mappings"
    )
    
    data["similarity"] = load_json(
        get_standard_similarity_path(root, standard),
        "Similarity results"
    )
    
    data["progress"] = load_json(
        get_verification_progress_path(root, standard),
        "Verification progress"
    )
    
    # Extracted text - required, fail immediately if missing
    extracted_text_path = get_standard_extracted_text_path(root, standard)
    if not extracted_text_path.exists():
        print(f"ERROR: Extracted text not found for {standard}.", file=sys.stderr)
        print(f"       Expected at: {extracted_text_path}", file=sys.stderr)
        print("       Run the text extraction first.", file=sys.stderr)
        sys.exit(1)
    data["extracted_text"] = load_json(extracted_text_path, f"{standard} extracted text")
    
    # ADD-6 data
    data["add6"] = load_add6_data(root)
    print(f"  Loaded ADD-6 data for {len(data['add6'])} guidelines", file=sys.stderr)
    
    # FLS chapter files
    fls_dir = get_fls_dir(root)
    data["fls_chapters"] = {}
    data["fls_index"] = load_json(get_fls_index_path(root), "FLS index")
    
    for chapter_info in data["fls_index"]["chapters"]:
        chapter_num = chapter_info["chapter"]
        chapter_path = get_fls_chapter_path(root, chapter_num)
        if chapter_path.exists():
            data["fls_chapters"][chapter_num] = load_json(chapter_path, f"FLS chapter {chapter_num}")
    
    # FLS section mapping
    data["fls_section_mapping"] = load_json(
        get_fls_section_mapping_path(root),
        "FLS section mapping"
    )
    
    return data


def get_batch_guidelines(data: dict, batch_id: int) -> list[str]:
    """Get the list of guideline IDs for a specific batch."""
    for batch in data["progress"]["batches"]:
        if batch["batch_id"] == batch_id:
            return [g["guideline_id"] for g in batch["guidelines"]]
    
    print(f"ERROR: Batch {batch_id} not found in progress.json", file=sys.stderr)
    sys.exit(1)


def get_mapping(data: dict, guideline_id: str) -> dict:
    """Get the current mapping for a guideline."""
    for m in data["mappings"]["mappings"]:
        if m["guideline_id"] == guideline_id:
            return m
    return {}


def get_rationale(data: dict, guideline_id: str) -> str:
    """Get the rationale text for a guideline."""
    for g in data["extracted_text"]["guidelines"]:
        if g["guideline_id"] == guideline_id:
            return g.get("rationale", "")
    return ""


def get_similarity_data(data: dict, guideline_id: str, section_threshold: float, paragraph_threshold: float) -> dict:
    """Get filtered similarity matches for a guideline."""
    sim = data["similarity"]["results"].get(guideline_id, {})
    
    section_matches = [
        m for m in sim.get("top_matches", [])
        if m["similarity"] >= section_threshold
    ]
    
    paragraph_matches = [
        m for m in sim.get("top_paragraph_matches", [])
        if m["similarity"] >= paragraph_threshold
    ]
    
    return {
        "top_section_matches": section_matches,
        "top_paragraph_matches": paragraph_matches,
    }


def find_section_in_chapters(data: dict, fls_id: str) -> dict | None:
    """Find a section by FLS ID across all chapters."""
    for chapter_num, chapter in data["fls_chapters"].items():
        for section in chapter.get("sections", []):
            if section.get("fls_id") == fls_id:
                return {
                    "chapter": chapter_num,
                    "section": section,
                    "chapter_fls_id": chapter.get("fls_id"),
                }
    return None


def get_sibling_sections(data: dict, section_info: dict) -> list[dict]:
    """Get sibling sections (same parent) for a section."""
    if not section_info:
        return []
    
    chapter_num = section_info["chapter"]
    section = section_info["section"]
    parent_fls_id = section.get("parent_fls_id")
    section_fls_id = section.get("fls_id")
    
    if not parent_fls_id:
        return []
    
    siblings = []
    chapter = data["fls_chapters"].get(chapter_num, {})
    
    for s in chapter.get("sections", []):
        if s.get("parent_fls_id") == parent_fls_id and s.get("fls_id") != section_fls_id:
            siblings.append({
                "chapter": chapter_num,
                "section": s,
            })
    
    return siblings


def format_section_content(section_info: dict, match_source: str) -> dict:
    """Format a section for the batch report."""
    section = section_info["section"]
    
    # Format rubrics
    rubrics = {}
    for cat_key, cat_data in section.get("rubrics", {}).items():
        cat_code = int(cat_key)
        cat_name = CATEGORY_NAMES.get(cat_code, f"unknown_{cat_code}")
        rubrics[cat_key] = {
            "category_name": cat_name,
            "paragraphs": cat_data.get("paragraphs", {}),
        }
    
    return {
        "fls_id": section.get("fls_id"),
        "title": section.get("title"),
        "chapter": section_info["chapter"],
        "fls_section": section.get("fls_section", ""),
        "content": section.get("content", ""),
        "match_source": match_source,
        "rubrics": rubrics,
    }


def extract_fls_content(data: dict, similarity_data: dict) -> dict:
    """
    Extract wide-shot FLS content for matched sections plus siblings.
    
    Strategy:
    1. Collect all unique section FLS IDs from section matches and paragraph matches
    2. For each matched section, include the section + all rubrics
    3. Unconditionally include sibling sections (same parent)
    """
    sections_to_include = {}  # fls_id -> (section_info, match_source)
    
    # Collect from section matches
    for match in similarity_data.get("top_section_matches", []):
        fls_id = match["fls_id"]
        if fls_id not in sections_to_include:
            section_info = find_section_in_chapters(data, fls_id)
            if section_info:
                sections_to_include[fls_id] = (section_info, "section_match")
    
    # Collect from paragraph matches (use section_fls_id)
    for match in similarity_data.get("top_paragraph_matches", []):
        section_fls_id = match.get("section_fls_id")
        if section_fls_id and section_fls_id not in sections_to_include:
            section_info = find_section_in_chapters(data, section_fls_id)
            if section_info:
                sections_to_include[section_fls_id] = (section_info, "paragraph_match")
    
    # Add siblings for all matched sections
    siblings_to_add = []
    for fls_id, (section_info, _) in list(sections_to_include.items()):
        siblings = get_sibling_sections(data, section_info)
        for sibling in siblings:
            sibling_fls_id = sibling["section"].get("fls_id")
            if sibling_fls_id and sibling_fls_id not in sections_to_include:
                siblings_to_add.append((sibling_fls_id, sibling, "sibling"))
    
    for sibling_fls_id, sibling_info, source in siblings_to_add:
        if sibling_fls_id not in sections_to_include:
            sections_to_include[sibling_fls_id] = (sibling_info, source)
    
    # Format all sections
    formatted_sections = []
    for fls_id, (section_info, match_source) in sections_to_include.items():
        formatted_sections.append(format_section_content(section_info, match_source))
    
    # Sort by chapter and section number
    formatted_sections.sort(key=lambda s: (s["chapter"], s.get("fls_section", "")))
    
    return {"sections": formatted_sections}


def build_scaffolded_context_decision() -> dict:
    """Build a scaffolded v2/v3 context decision structure."""
    return {
        "decision": None,           # Required: "accept_with_modifications", "accept_no_matches", "accept_existing", "reject", "pending"
        "applicability": None,      # Required: "yes", "no", "partial"
        "adjusted_category": None,  # Required: "required", "advisory", "recommended", "disapplied", "implicit", "n_a"
        "rationale_type": None,     # Required: "direct_mapping", "partial_mapping", "rust_alternative", "rust_prevents", "no_equivalent"
        "confidence": None,         # Required: "high", "medium", "low"
        "accepted_matches": [],     # Required: array of FLS matches
        "rejected_matches": [],     # Optional: array of explicitly rejected matches
        "search_tools_used": [],    # Required: array of search tool records
        "notes": None,              # Optional: additional notes
    }


def build_scaffolded_v1_decision() -> dict:
    """Build a scaffolded v1 verification decision structure."""
    return {
        "decision": None,           # Required: "accept_with_modifications", "accept_no_matches", "accept_existing", "reject"
        "confidence": None,         # Required: "high", "medium", "low"
        "fls_rationale_type": None, # Required: "direct_mapping", "rust_alternative", "rust_prevents", "no_equivalent", "partial_mapping"
        "accepted_matches": [],     # Required: array of FLS matches with fls_id, category, score, reason
        "rejected_matches": [],     # Optional: array of explicitly rejected matches
        "search_tools_used": [],    # Required: array of search tool records
        "notes": None,              # Optional: additional notes
    }


def build_scaffolded_v2_decision() -> dict:
    """Build a scaffolded v2/v3 verification decision structure."""
    return {
        "all_rust": build_scaffolded_context_decision(),
        "safe_rust": build_scaffolded_context_decision(),
    }


def build_current_state_from_mapping(mapping: dict) -> dict:
    """
    Build current_state from a mapping entry.
    
    Handles v1.x (flat) and v2.x/v3.x/v4.x (per-context) mapping formats.
    """
    version = get_guideline_schema_version(mapping)
    
    # Per-context versions
    per_context_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    
    # For v2+ entries, include both flat (for backwards compat) and per-context
    if version in per_context_versions:
        all_rust = mapping.get("all_rust", {})
        safe_rust = mapping.get("safe_rust", {})
        return {
            "schema_version": version,
            # v1-style fields for backwards compatibility
            "applicability_all_rust": all_rust.get("applicability"),
            "applicability_safe_rust": safe_rust.get("applicability"),
            "confidence": all_rust.get("confidence"),
            "fls_rationale_type": all_rust.get("rationale_type"),
            "accepted_matches": all_rust.get("accepted_matches", []),
            "rejected_matches": all_rust.get("rejected_matches", []),
            "notes": all_rust.get("notes"),
            # Full per-context data
            "all_rust": all_rust,
            "safe_rust": safe_rust,
            # ADD-6 if present
            "misra_add6": mapping.get("misra_add6"),
        }
    else:
        # v1.x entries (v1.0, v1.1, v1.2)
        return {
            "schema_version": version,
            "applicability_all_rust": mapping.get("applicability_all_rust"),
            "applicability_safe_rust": mapping.get("applicability_safe_rust"),
            "confidence": mapping.get("confidence"),
            "fls_rationale_type": mapping.get("fls_rationale_type"),
            "accepted_matches": mapping.get("accepted_matches", []),
            "rejected_matches": mapping.get("rejected_matches", []),
            "notes": mapping.get("notes"),
            # ADD-6 if present (v1.1+)
            "misra_add6": mapping.get("misra_add6"),
        }


def build_guideline_entry(
    data: dict,
    guideline_id: str,
    section_threshold: float,
    paragraph_threshold: float,
    schema_version: SchemaVersion = "4.0",
) -> dict:
    """Build a complete guideline entry for the batch report."""
    mapping = get_mapping(data, guideline_id)
    rationale = get_rationale(data, guideline_id)
    similarity_data = get_similarity_data(data, guideline_id, section_threshold, paragraph_threshold)
    fls_content = extract_fls_content(data, similarity_data)
    
    # Get ADD-6 data for this guideline
    add6 = data.get("add6", {}).get(guideline_id)
    
    # Per-context versions use v2-style scaffolded decision
    per_context_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    
    # Build verification_decision based on schema version
    if schema_version in per_context_versions:
        verification_decision = build_scaffolded_v2_decision()
    else:
        verification_decision = build_scaffolded_v1_decision()
    
    # Build current_state from mapping (handles all versions)
    current_state = build_current_state_from_mapping(mapping)
    
    entry = {
        "guideline_id": guideline_id,
        "guideline_title": mapping.get("guideline_title", ""),
        "current_state": current_state,
        "rationale": rationale,
        "similarity_data": similarity_data,
        "fls_content": fls_content,
        # Scaffolded verification_decision structure - to be filled by LLM/tool in Phase 2
        # See coding-standards-fls-mapping/schema/batch_report.schema.json for required fields
        "verification_decision": verification_decision,
    }
    
    # For v3.0+ batch reports, include ADD-6 data at the guideline level
    add6_versions = ("3.0", "3.1", "3.2", "4.0")
    if schema_version in add6_versions and add6:
        entry["misra_add6"] = build_misra_add6_block(add6)
    elif schema_version in add6_versions and not add6:
        print(f"  WARNING: No ADD-6 data for {guideline_id}", file=sys.stderr)
    
    return entry


def build_batch_report(
    data: dict,
    standard: str,
    batch_id: int,
    session_id: int,
    section_threshold: float,
    paragraph_threshold: float,
    schema_version: SchemaVersion = "4.0",
) -> dict:
    """Build the complete batch report."""
    guideline_ids = get_batch_guidelines(data, batch_id)
    
    guidelines = []
    for gid in guideline_ids:
        entry = build_guideline_entry(
            data, gid, section_threshold, paragraph_threshold, schema_version
        )
        guidelines.append(entry)
    
    # Use internal standard name
    internal_standard = normalize_standard(standard)
    
    # Per-context versions
    per_context_versions = ("2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0")
    
    # Build summary based on schema version
    summary = {
        "total_guidelines": len(guidelines),
        "verified_count": 0,
        "applicability_changes_proposed": 0,
        "applicability_changes_approved": 0,
    }
    
    # Add per-context counts for v2+
    if schema_version in per_context_versions:
        summary["all_rust_verified_count"] = 0
        summary["safe_rust_verified_count"] = 0
    
    return {
        "schema_version": schema_version,
        "batch_id": batch_id,
        "session_id": session_id,
        "generated_date": date.today().isoformat(),
        "standard": internal_standard,
        "thresholds": {
            "section": section_threshold,
            "paragraph": paragraph_threshold,
        },
        "guidelines": guidelines,
        "applicability_changes": [],  # To be populated in Phase 2
        "summary": summary,
    }


def generate_human_report(report: dict) -> str:
    """Generate a human-readable Markdown report."""
    lines = []
    
    lines.append(f"# Batch {report['batch_id']} Verification Report")
    lines.append(f"")
    lines.append(f"**Session:** {report['session_id']}")
    lines.append(f"**Generated:** {report['generated_date']}")
    lines.append(f"**Standard:** {report['standard']}")
    lines.append(f"**Thresholds:** section={report['thresholds']['section']}, paragraph={report['thresholds']['paragraph']}")
    lines.append(f"**Total Guidelines:** {report['summary']['total_guidelines']}")
    lines.append(f"")
    
    # Summary table
    lines.append("## Guidelines Summary")
    lines.append("")
    lines.append("| # | Guideline | Title | Appl (all) | Appl (safe) | Confidence | Section Matches | Paragraph Matches |")
    lines.append("|---|-----------|-------|------------|-------------|------------|-----------------|-------------------|")
    
    for i, g in enumerate(report["guidelines"], 1):
        gid = g["guideline_id"]
        title = g["guideline_title"][:40] + "..." if len(g["guideline_title"]) > 40 else g["guideline_title"]
        appl_all = g["current_state"].get("applicability_all_rust", "N/A")
        appl_safe = g["current_state"].get("applicability_safe_rust", "N/A")
        conf = g["current_state"].get("confidence", "N/A")
        sec_matches = len(g["similarity_data"]["top_section_matches"])
        para_matches = len(g["similarity_data"]["top_paragraph_matches"])
        
        lines.append(f"| {i} | {gid} | {title} | {appl_all} | {appl_safe} | {conf} | {sec_matches} | {para_matches} |")
    
    lines.append("")
    
    # Detailed sections for each guideline
    lines.append("## Guideline Details")
    lines.append("")
    
    for g in report["guidelines"]:
        lines.append(f"### {g['guideline_id']}: {g['guideline_title']}")
        lines.append("")
        
        # Current state
        lines.append("**Current State:**")
        lines.append(f"- Applicability (all Rust): `{g['current_state'].get('applicability_all_rust')}`")
        lines.append(f"- Applicability (safe Rust): `{g['current_state'].get('applicability_safe_rust')}`")
        lines.append(f"- Confidence: `{g['current_state'].get('confidence')}`")
        lines.append(f"- FLS Rationale Type: `{g['current_state'].get('fls_rationale_type')}`")
        lines.append("")
        
        # Rationale (truncated for human report)
        if g.get("rationale"):
            rationale = g["rationale"][:500]
            if len(g["rationale"]) > 500:
                rationale += "..."
            lines.append("**Rationale:**")
            lines.append(f"> {rationale}")
            lines.append("")
        
        # Top matches
        if g["similarity_data"]["top_section_matches"]:
            lines.append("**Top Section Matches:**")
            for m in g["similarity_data"]["top_section_matches"][:5]:
                lines.append(f"- `{m['fls_id']}`: {m['similarity']:.3f} - {m['title']}")
            lines.append("")
        
        if g["similarity_data"]["top_paragraph_matches"]:
            lines.append("**Top Paragraph Matches:**")
            for m in g["similarity_data"]["top_paragraph_matches"][:5]:
                preview = m["text_preview"][:80] + "..." if len(m["text_preview"]) > 80 else m["text_preview"]
                lines.append(f"- `{m['fls_id']}`: {m['similarity']:.3f} [{m['category_name']}] {preview}")
            lines.append("")
        
        # FLS content summary
        fls_sections = g["fls_content"]["sections"]
        if fls_sections:
            lines.append(f"**FLS Sections Extracted:** {len(fls_sections)}")
            for s in fls_sections[:10]:
                source_badge = f"[{s['match_source']}]"
                lines.append(f"- `{s['fls_id']}`: {s['title']} {source_badge}")
            if len(fls_sections) > 10:
                lines.append(f"- ... and {len(fls_sections) - 10} more")
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Data gathering for FLS verification"
    )
    parser.add_argument(
        "--standard", "-s",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c, misra-cpp, cert-c, cert-cpp)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        required=True,
        help="Batch number from progress.json",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=1,
        help="Session ID for this verification run",
    )
    parser.add_argument(
        "--mode",
        choices=["llm", "human"],
        default="llm",
        help="Output mode: llm (full JSON) or human (Markdown summary)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (defaults to stdout for human mode)",
    )
    parser.add_argument(
        "--section-threshold",
        type=float,
        default=DEFAULT_SECTION_THRESHOLD,
        help=f"Minimum section similarity score (default: {DEFAULT_SECTION_THRESHOLD})",
    )
    parser.add_argument(
        "--paragraph-threshold",
        type=float,
        default=DEFAULT_PARAGRAPH_THRESHOLD,
        help=f"Minimum paragraph similarity score (default: {DEFAULT_PARAGRAPH_THRESHOLD})",
    )
    parser.add_argument(
        "--schema-version",
        type=str,
        choices=["1.0", "2.0", "3.0", "4.0"],
        default="4.0",
        help="Schema version to generate (default: 4.0)",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    standard = args.standard
    schema_version: SchemaVersion = args.schema_version
    
    print(f"Loading data for {standard}...", file=sys.stderr)
    data = load_all_data(root, standard)
    
    print(f"Loading batch report schema...", file=sys.stderr)
    schema = load_batch_report_schema(root)
    
    print(f"Building batch {args.batch} report (schema {schema_version})...", file=sys.stderr)
    report = build_batch_report(
        data,
        standard,
        args.batch,
        args.session,
        args.section_threshold,
        args.paragraph_threshold,
        schema_version,
    )
    
    # Validate the generated report against the schema
    if schema:
        print(f"Validating batch report against schema...", file=sys.stderr)
        errors = validate_batch_report(report, schema)
        if errors:
            print("WARNING: Generated report has schema validation issues:", file=sys.stderr)
            for err in errors:
                print(f"  {err}", file=sys.stderr)
            print("  (This is expected for newly generated reports with unfilled verification_decision)", file=sys.stderr)
    
    if args.mode == "llm":
        output = json.dumps(report, indent=2)
    else:
        output = generate_human_report(report)
    
    if args.output:
        # Resolve and validate output path
        try:
            output_path = resolve_path(Path(args.output))
            output_path = validate_path_in_project(output_path, root)
        except PathOutsideProjectError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(output)
        print(f"Report written to {output_path}", file=sys.stderr)
    else:
        print(output)
    
    print(f"Done. Processed {len(report['guidelines'])} guidelines.", file=sys.stderr)


if __name__ == "__main__":
    main()
