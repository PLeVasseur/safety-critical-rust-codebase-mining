#!/usr/bin/env python3
"""
Map MISRA C:2025 guidelines to Ferrocene Language Specification (FLS) sections.

This script uses semantic similarity embeddings to match MISRA guidelines to FLS
sections and paragraphs, generating the `accepted_matches` format.

Two modes of operation:
1. Similarity mode (default): Uses pre-computed embeddings from the similarity pipeline
2. Legacy mode (--no-similarity): Uses keyword matching against concept_to_fls.json

Usage:
    uv run python map_misra_to_fls.py [options]
    
Options:
    --section-threshold FLOAT   Min section similarity score (default: 0.5)
    --paragraph-threshold FLOAT Min paragraph similarity score (default: 0.55)
    --max-section-matches INT   Max sections per guideline (default: 5)
    --max-paragraph-matches INT Max paragraphs per guideline (default: 10)
    --no-similarity             Use legacy keyword matching instead
    --no-preserve               Overwrite existing high-confidence entries
    --limit N                   Process only first N guidelines (for testing)
    --output PATH               Output file path
    --verbose                   Print detailed matching information
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


# Category code to human-readable name mapping
CATEGORY_NAMES = {
    0: "section",
    -1: "general",
    -2: "legality_rules",
    -3: "dynamic_semantics",
    -4: "undefined_behavior",
    -5: "implementation_requirements",
    -6: "implementation_permissions",
    -7: "examples",
    -8: "syntax",
}


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, path: Path) -> None:
    """Save data to a JSON file with pretty formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {path}")


def load_fls_section_mapping(tools_dir: Path) -> dict:
    """
    Load FLS section mapping and build a lookup from fls_id to section number.
    Returns dict: fls_id -> {"section": "15.2", "title": "References", ...}
    """
    mapping_path = tools_dir / "fls_section_mapping.json"
    if not mapping_path.exists():
        print(f"Warning: FLS section mapping not found at {mapping_path}")
        return {}
    
    with open(mapping_path, encoding="utf-8") as f:
        mapping = json.load(f)
    
    lookup = {}
    
    def process_sections(sections: dict, parent_chapter: str = ""):
        for key, section_data in sections.items():
            if key.startswith("_"):
                # Fabricated section (e.g., _legality_rules)
                fls_section = section_data.get("fls_section", "")
                fls_id = section_data.get("fls_id")
                title = section_data.get("title", "")
                
                if fls_id:
                    lookup[fls_id] = {
                        "section": fls_section,
                        "title": title,
                        "category": section_data.get("category", 0),
                    }
                
                # Process subsections
                if "subsections" in section_data:
                    for sub_key, sub_data in section_data["subsections"].items():
                        sub_fls_id = sub_data.get("fls_id")
                        if sub_fls_id:
                            lookup[sub_fls_id] = {
                                "section": sub_data.get("fls_section", ""),
                                "title": sub_data.get("title", ""),
                                "category": sub_data.get("category", 0),
                            }
            else:
                # Regular section
                fls_section = section_data.get("fls_section", "")
                fls_id = section_data.get("fls_id")
                title = section_data.get("title", "")
                
                if fls_id:
                    lookup[fls_id] = {
                        "section": fls_section,
                        "title": title,
                        "category": 0,  # Regular sections are category 0
                    }
                
                # Process nested sections
                if "sections" in section_data:
                    process_sections(section_data["sections"], fls_section)
    
    for chapter_num, chapter_data in mapping.items():
        if not chapter_num.isdigit():
            continue
        
        fls_id = chapter_data.get("fls_id")
        if fls_id:
            lookup[fls_id] = {
                "section": chapter_num,
                "title": chapter_data.get("title", ""),
                "category": 0,
            }
        
        if "sections" in chapter_data:
            process_sections(chapter_data["sections"], chapter_num)
    
    return lookup


def load_similarity_results(project_root: Path) -> dict | None:
    """Load pre-computed similarity results."""
    sim_path = project_root / "embeddings" / "similarity" / "misra_c_to_fls.json"
    if not sim_path.exists():
        print(f"Warning: Similarity results not found at {sim_path}")
        return None
    
    with open(sim_path, encoding="utf-8") as f:
        return json.load(f)


def load_existing_mappings(output_path: Path) -> dict:
    """Load existing mappings to preserve high-confidence entries."""
    if not output_path.exists():
        return {}
    
    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)
    
    # Build lookup by guideline_id
    lookup = {}
    for m in data.get("mappings", []):
        gid = m.get("guideline_id")
        if gid:
            lookup[gid] = m
    
    return lookup


def convert_misra_applicability(misra_app: str, misra_category: str | None = None) -> str:
    """Convert MISRA ADD-6 applicability to our schema values."""
    if misra_category and misra_category.lower() == "implicit":
        return "rust_prevents"
    
    mapping = {
        "Yes": "direct",
        "No": "not_applicable", 
        "Partial": "partial"
    }
    return mapping.get(misra_app, "unmapped")


def convert_misra_category(misra_cat: str) -> str | None:
    """Convert MISRA ADD-6 adjusted category to our schema values."""
    mapping = {
        "required": "required",
        "advisory": "advisory",
        "recommended": "recommended",
        "disapplied": "disapplied",
        "implicit": "implicit",
        "n_a": "n_a"
    }
    return mapping.get(misra_cat.lower() if misra_cat else "", None)


def determine_fls_rationale_type(
    applicability_all: str,
    applicability_safe: str,
    has_matches: bool
) -> str | None:
    """Determine the fls_rationale_type based on applicability."""
    if not has_matches:
        return None
    
    if applicability_all == "rust_prevents" or applicability_safe == "rust_prevents":
        return "rust_prevents"
    elif applicability_all == "not_applicable":
        return "no_equivalent"
    elif applicability_all == "partial" or applicability_safe == "partial":
        return "partial_mapping"
    elif applicability_all == "direct":
        return "direct_mapping"
    else:
        return "partial_mapping"


def truncate_text(text: str, max_len: int = 80) -> str:
    """Truncate text to max length, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."


def create_accepted_matches_from_similarity(
    guideline_id: str,
    similarity_results: dict,
    fls_section_lookup: dict,
    section_threshold: float,
    paragraph_threshold: float,
    max_section_matches: int,
    max_paragraph_matches: int,
    verbose: bool = False
) -> list[dict]:
    """
    Create accepted_matches entries from similarity results.
    
    Returns list of match dicts with: fls_id, category, fls_section, fls_title, score, reason
    """
    result = similarity_results.get("results", {}).get(guideline_id)
    if not result:
        if verbose:
            print(f"  No similarity results for {guideline_id}")
        return []
    
    accepted = []
    seen_fls_ids = set()
    
    # Process paragraph matches first (higher precision)
    para_matches = result.get("top_paragraph_matches", [])
    para_count = 0
    
    for match in para_matches:
        if para_count >= max_paragraph_matches:
            break
        
        score = match.get("similarity", 0)
        if score < paragraph_threshold:
            continue
        
        fls_id = match.get("fls_id")
        if fls_id in seen_fls_ids:
            continue
        
        seen_fls_ids.add(fls_id)
        
        # Get section info from lookup or match metadata
        section_info = fls_section_lookup.get(fls_id, {})
        fls_section = section_info.get("section") or match.get("section_fls_id", "")
        fls_title = match.get("section_title") or section_info.get("title", "")
        category = match.get("category", -2)  # Default to legality_rules for paragraphs
        
        # Build reason with text preview
        text_preview = match.get("text_preview", "")
        if text_preview:
            reason = f"Per FLS: '{truncate_text(text_preview, 70)}' (similarity: {score:.2f})"
        else:
            reason = f"Semantic similarity match (score: {score:.2f})"
        
        accepted.append({
            "fls_id": fls_id,
            "category": category,
            "fls_section": fls_section if fls_section else None,
            "fls_title": fls_title or match.get("title", ""),
            "score": round(score, 3),
            "reason": reason,
        })
        
        para_count += 1
    
    # Process section matches (coarse, for coverage)
    section_matches = result.get("top_matches", [])
    section_count = 0
    
    for match in section_matches:
        if section_count >= max_section_matches:
            break
        
        score = match.get("similarity", 0)
        if score < section_threshold:
            continue
        
        fls_id = match.get("fls_id")
        if fls_id in seen_fls_ids:
            continue
        
        seen_fls_ids.add(fls_id)
        
        # Get section info from lookup
        section_info = fls_section_lookup.get(fls_id, {})
        fls_section = section_info.get("section", "")
        fls_title = match.get("title") or section_info.get("title", "")
        category = match.get("category", 0)  # Sections are category 0
        
        reason = f"Section-level similarity match (score: {score:.2f})"
        
        accepted.append({
            "fls_id": fls_id,
            "category": category,
            "fls_section": fls_section if fls_section else None,
            "fls_title": fls_title,
            "score": round(score, 3),
            "reason": reason,
        })
        
        section_count += 1
    
    # Sort by score descending
    accepted.sort(key=lambda x: x["score"], reverse=True)
    
    if verbose and accepted:
        print(f"  {len(accepted)} matches (paragraphs: {para_count}, sections: {section_count})")
    
    return accepted


def generate_notes(
    misra_rust_data: dict | None,
    applicability_all: str,
    applicability_safe: str,
    num_matches: int
) -> str:
    """Generate notes explaining the mapping."""
    notes_parts = []
    
    # Add MISRA's comment if available
    if misra_rust_data and misra_rust_data.get("comment"):
        notes_parts.append(f"MISRA ADD-6: {misra_rust_data['comment']}")
    
    # Add applicability explanation if different between all/safe
    if applicability_all != applicability_safe:
        if applicability_safe == "rust_prevents" and applicability_all == "partial":
            notes_parts.append("Safe Rust prevents this issue; applies to unsafe code")
        elif applicability_safe == "not_applicable" and applicability_all != "not_applicable":
            notes_parts.append("Only applicable in unsafe Rust")
    
    if not notes_parts:
        if num_matches > 0:
            notes_parts.append("Similarity-based mapping - requires manual verification")
        else:
            notes_parts.append("No high-confidence FLS matches found")
    
    return ". ".join(notes_parts)


def create_mapping_entry_from_similarity(
    guideline: dict,
    misra_rust_data: dict | None,
    similarity_results: dict,
    fls_section_lookup: dict,
    section_threshold: float,
    paragraph_threshold: float,
    max_section_matches: int,
    max_paragraph_matches: int,
    verbose: bool = False
) -> dict:
    """Create a single mapping entry using similarity-based matching."""
    guideline_id = guideline["id"]
    title = guideline.get("title", "")
    guideline_type = guideline.get("guideline_type", "rule")
    
    if verbose:
        print(f"\n{guideline_id}: {title[:50]}...")
    
    # Get applicability from MISRA ADD-6
    if misra_rust_data:
        raw_category = misra_rust_data.get("adjusted_category", "")
        applicability_all = convert_misra_applicability(
            misra_rust_data.get("applicability_all_rust", ""), raw_category
        )
        applicability_safe = convert_misra_applicability(
            misra_rust_data.get("applicability_safe_rust", ""), raw_category
        )
        misra_category = convert_misra_category(raw_category)
        misra_comment = misra_rust_data.get("comment") or None
    else:
        applicability_all = "unmapped"
        applicability_safe = "unmapped"
        misra_category = None
        misra_comment = None
    
    # Get similarity-based matches
    accepted_matches = create_accepted_matches_from_similarity(
        guideline_id,
        similarity_results,
        fls_section_lookup,
        section_threshold,
        paragraph_threshold,
        max_section_matches,
        max_paragraph_matches,
        verbose
    )
    
    # Generate notes
    notes = generate_notes(
        misra_rust_data, applicability_all, applicability_safe, len(accepted_matches)
    )
    
    # Build entry
    entry = {
        "guideline_id": guideline_id,
        "guideline_title": title,
        "guideline_type": guideline_type,
        "applicability_all_rust": applicability_all,
        "applicability_safe_rust": applicability_safe,
    }
    
    # Add accepted_matches if we have any
    if accepted_matches:
        entry["accepted_matches"] = accepted_matches
        rationale_type = determine_fls_rationale_type(
            applicability_all, applicability_safe, True
        )
        if rationale_type:
            entry["fls_rationale_type"] = rationale_type
    
    # Add MISRA-specific fields
    if misra_category:
        entry["misra_rust_category"] = misra_category
    if misra_comment:
        entry["misra_rust_comment"] = misra_comment
    
    # Set confidence to medium for all automated mappings
    entry["confidence"] = "medium"
    entry["notes"] = notes
    
    return entry


def main():
    parser = argparse.ArgumentParser(description="Map MISRA C:2025 guidelines to FLS")
    parser.add_argument("--section-threshold", type=float, default=0.5,
                       help="Minimum section similarity score (default: 0.5)")
    parser.add_argument("--paragraph-threshold", type=float, default=0.55,
                       help="Minimum paragraph similarity score (default: 0.55)")
    parser.add_argument("--max-section-matches", type=int, default=5,
                       help="Max section matches per guideline (default: 5)")
    parser.add_argument("--max-paragraph-matches", type=int, default=10,
                       help="Max paragraph matches per guideline (default: 10)")
    parser.add_argument("--no-similarity", action="store_true",
                       help="Use legacy keyword matching instead of similarity")
    parser.add_argument("--no-preserve", action="store_true",
                       help="Overwrite existing high-confidence entries")
    parser.add_argument("--limit", type=int, help="Process only first N guidelines")
    parser.add_argument("--output", type=str, help="Output file path")
    parser.add_argument("--verbose", action="store_true", help="Print detailed matching info")
    args = parser.parse_args()
    
    # Paths
    project_root = Path(__file__).parent.parent
    base_dir = project_root / "coding-standards-fls-mapping"
    tools_dir = Path(__file__).parent
    
    standards_path = base_dir / "standards" / "misra_c_2025.json"
    rust_app_path = base_dir / "misra_rust_applicability.json"
    output_path = Path(args.output) if args.output else base_dir / "mappings" / "misra_c_to_fls.json"
    
    # Load data
    print("Loading data...")
    standards = load_json(standards_path)
    rust_applicability = load_json(rust_app_path)
    
    # Extract all guidelines from categories
    all_guidelines = []
    for category in standards.get("categories", []):
        for guideline in category.get("guidelines", []):
            all_guidelines.append(guideline)
    
    print(f"Loaded {len(all_guidelines)} guidelines from MISRA C:2025")
    print(f"Loaded {len(rust_applicability.get('guidelines', {}))} guidelines from MISRA ADD-6")
    
    # Load existing mappings to preserve high-confidence entries
    existing_mappings = {}
    if not args.no_preserve:
        existing_mappings = load_existing_mappings(output_path)
        preserved_count = sum(
            1 for m in existing_mappings.values()
            if m.get("confidence") == "high" and m.get("accepted_matches")
        )
        print(f"Found {preserved_count} high-confidence entries to preserve")
    
    # Load FLS section lookup
    fls_section_lookup = load_fls_section_mapping(tools_dir)
    print(f"Loaded {len(fls_section_lookup)} FLS section mappings")
    
    # Load similarity results
    similarity_results = None
    if not args.no_similarity:
        similarity_results = load_similarity_results(project_root)
        if similarity_results:
            print(f"Loaded similarity results for {len(similarity_results.get('results', {}))} guidelines")
            print(f"  Thresholds: section >= {args.section_threshold}, paragraph >= {args.paragraph_threshold}")
        else:
            print("Warning: No similarity results found, falling back to empty matches")
    
    if args.limit:
        all_guidelines = all_guidelines[:args.limit]
        print(f"Limited to {len(all_guidelines)} guidelines")
    
    # Process guidelines
    print("\nProcessing guidelines...")
    mappings = []
    rust_guidelines = rust_applicability.get("guidelines", {})
    
    # Statistics
    stats = {
        "total": 0,
        "preserved": 0,
        "with_matches": 0,
        "without_matches": 0,
        "by_applicability": {},
        "by_category": {},
        "total_matches": 0,
    }
    
    for guideline in all_guidelines:
        guideline_id = guideline["id"]
        misra_rust_data = rust_guidelines.get(guideline_id)
        
        # Check if we should preserve existing entry
        existing = existing_mappings.get(guideline_id)
        if existing and existing.get("confidence") == "high" and existing.get("accepted_matches"):
            if not args.no_preserve:
                # Preserve the existing high-confidence entry
                # But first, fix any legacy matches that are missing category
                def fix_matches(matches: list) -> list:
                    fixed = []
                    for match in matches:
                        if "category" not in match:
                            fls_id = match.get("fls_id")
                            section_info = fls_section_lookup.get(fls_id, {})
                            match = dict(match)  # Make a copy
                            match["category"] = section_info.get("category", 0)
                        fixed.append(match)
                    return fixed
                
                preserved_entry = dict(existing)
                preserved_entry["accepted_matches"] = fix_matches(existing.get("accepted_matches", []))
                
                # Also fix rejected_matches if present
                if existing.get("rejected_matches"):
                    preserved_entry["rejected_matches"] = fix_matches(existing.get("rejected_matches", []))
                
                mappings.append(preserved_entry)
                stats["total"] += 1
                stats["preserved"] += 1
                stats["with_matches"] += 1
                stats["total_matches"] += len(preserved_entry["accepted_matches"])
                
                # Track applicability
                app_all = existing.get("applicability_all_rust", "unmapped")
                stats["by_applicability"][app_all] = stats["by_applicability"].get(app_all, 0) + 1
                
                if args.verbose:
                    print(f"\n{guideline_id}: PRESERVED (high confidence, {len(preserved_entry['accepted_matches'])} matches)")
                continue
        
        # Create new entry from similarity
        if similarity_results:
            entry = create_mapping_entry_from_similarity(
                guideline,
                misra_rust_data,
                similarity_results,
                fls_section_lookup,
                args.section_threshold,
                args.paragraph_threshold,
                args.max_section_matches,
                args.max_paragraph_matches,
                args.verbose
            )
        else:
            # Minimal entry when no similarity data
            entry = {
                "guideline_id": guideline_id,
                "guideline_title": guideline.get("title", ""),
                "guideline_type": guideline.get("guideline_type", "rule"),
                "applicability_all_rust": "unmapped",
                "applicability_safe_rust": "unmapped",
                "confidence": "medium",
                "notes": "No similarity data available",
            }
            if misra_rust_data:
                raw_category = misra_rust_data.get("adjusted_category", "")
                entry["applicability_all_rust"] = convert_misra_applicability(
                    misra_rust_data.get("applicability_all_rust", ""), raw_category
                )
                entry["applicability_safe_rust"] = convert_misra_applicability(
                    misra_rust_data.get("applicability_safe_rust", ""), raw_category
                )
                if convert_misra_category(raw_category):
                    entry["misra_rust_category"] = convert_misra_category(raw_category)
        
        mappings.append(entry)
        
        # Update stats
        stats["total"] += 1
        
        accepted = entry.get("accepted_matches", [])
        if accepted:
            stats["with_matches"] += 1
            stats["total_matches"] += len(accepted)
            
            # Track by category
            for match in accepted:
                cat = match.get("category", 0)
                cat_name = CATEGORY_NAMES.get(cat, f"unknown_{cat}")
                stats["by_category"][cat_name] = stats["by_category"].get(cat_name, 0) + 1
        else:
            stats["without_matches"] += 1
        
        # Track applicability
        app_all = entry.get("applicability_all_rust", "unmapped")
        stats["by_applicability"][app_all] = stats["by_applicability"].get(app_all, 0) + 1
    
    # Calculate averages
    avg_matches = stats["total_matches"] / stats["total"] if stats["total"] > 0 else 0
    
    # Create output structure
    output = {
        "standard": "MISRA-C",
        "standard_version": "2025",
        "fls_version": "1.0 (2024)",
        "mapping_date": date.today().isoformat(),
        "methodology": "Semantic embedding similarity + manual verification. High confidence mappings verified against MISRA rationale and FLS content.",
        "statistics": {
            "total_guidelines": stats["total"],
            "mapped": stats["with_matches"],
            "unmapped": stats["without_matches"],
            "not_applicable": stats["by_applicability"].get("not_applicable", 0),
            "rust_prevents": stats["by_applicability"].get("rust_prevents", 0),
            "preserved_high_confidence": stats["preserved"],
            "avg_matches_per_guideline": round(avg_matches, 1),
            "matches_by_category": stats["by_category"],
            "thresholds": {
                "section": args.section_threshold,
                "paragraph": args.paragraph_threshold,
            },
        },
        "mappings": mappings
    }
    
    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(output, output_path)
    
    # Print summary
    print("\n" + "="*60)
    print("MAPPING SUMMARY")
    print("="*60)
    print(f"Total guidelines processed: {stats['total']}")
    print(f"  With FLS matches:    {stats['with_matches']}")
    print(f"  Without matches:     {stats['without_matches']}")
    print(f"  Preserved (high):    {stats['preserved']}")
    print(f"  Avg matches/guide:   {avg_matches:.1f}")
    print(f"\nBy applicability:")
    for app, count in sorted(stats["by_applicability"].items()):
        print(f"  {app}: {count}")
    print(f"\nMatches by FLS category:")
    for cat, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    print(f"\nThresholds used:")
    print(f"  Section: >= {args.section_threshold}")
    print(f"  Paragraph: >= {args.paragraph_threshold}")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
