#!/usr/bin/env python3
"""
search_fls_deep.py - Deep Semantic Search Across FLS Content

This script performs multi-query semantic search for a specific MISRA guideline
using ALL available embedding types:
1. Guideline-level embedding (combined title + rationale + amplification)
2. Query-level embeddings (individual concerns parsed from rationale)
3. Rationale-level embedding (full rationale with title context)
4. Amplification-level embedding (full amplification with title context)

Each embedding searches FLS sections and paragraphs independently, then results
are merged with deduplication (keeping highest score per FLS ID).

Additional features:
- Concept boost: Adds score bonus for FLS IDs in matched concepts
- See-also integration: Pulls top matches from referenced guidelines

Usage:
    uv run python verification/search_fls_deep.py --guideline "Rule 21.3"
    uv run python verification/search_fls_deep.py --guideline "Rule 21.3" --mode detailed
    uv run python verification/search_fls_deep.py --guideline "Rule 21.3" --no-concept-boost --no-see-also
"""

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from fls_tools.shared import (
    get_project_root,
    get_fls_dir,
    get_standard_extracted_text_path,
    get_concept_to_fls_path,
    get_standard_similarity_path,
    get_fls_section_embeddings_path,
    get_fls_paragraph_embeddings_path,
    get_standard_embeddings_path,
    get_standard_query_embeddings_path,
    get_standard_rationale_embeddings_path,
    get_standard_amplification_embeddings_path,
    get_misra_rust_applicability_path,
    CATEGORY_NAMES,
    CONCEPT_BOOST_ADDITIVE,
    CONCEPT_ONLY_BASE_SCORE,
    SEE_ALSO_SCORE_PENALTY,
    SEE_ALSO_MAX_MATCHES,
    VALID_STANDARDS,
    generate_search_id,
)

# Rationale code expansions for display
RATIONALE_CODE_NAMES = {
    "UB": "Undefined Behaviour",
    "IDB": "Implementation-defined Behaviour",
    "CQ": "Code Quality",
    "DC": "Design Consideration",
}


def load_embeddings(path: Path) -> tuple[list[str], np.ndarray, dict, dict]:
    """
    Load embeddings from pickle file.
    
    Returns:
        ids: List of IDs
        embeddings: numpy array of embeddings (N x D)
        id_to_index: Dict mapping ID to index
        metadata: Dict of metadata (if present)
    """
    if not path.exists():
        return [], np.array([]), {}, {}
    
    with open(path, "rb") as f:
        data = pickle.load(f)
    
    embed_data = data.get("data", data)
    
    ids = embed_data.get("ids", [])
    embeddings = embed_data.get("embeddings", np.array([]))
    id_to_index = embed_data.get("id_to_index", {})
    metadata = data.get("metadata", {})
    
    return ids, embeddings, id_to_index, metadata


def load_fls_chapters(root: Path) -> dict:
    """Load all FLS chapter files for content lookup."""
    chapters = {}
    fls_dir = get_fls_dir(root)
    
    for chapter_file in fls_dir.glob("chapter_*.json"):
        try:
            with open(chapter_file) as f:
                data = json.load(f)
                chapter_num = data.get("chapter")
                if chapter_num:
                    chapters[chapter_num] = data
        except (json.JSONDecodeError, KeyError):
            continue
    
    return chapters


def build_fls_metadata(chapters: dict) -> tuple[dict, dict]:
    """
    Build sections and paragraphs metadata dicts from loaded chapters.
    
    Returns:
        sections_metadata: Dict mapping fls_id -> {title, chapter, category}
        paragraphs_metadata: Dict mapping para_id -> {text, section_fls_id, ...}
    """
    sections_metadata = {}
    paragraphs_metadata = {}
    
    for chapter_num, chapter in chapters.items():
        for section in chapter.get("sections", []):
            fls_id = section.get("fls_id")
            if fls_id:
                sections_metadata[fls_id] = {
                    "title": section.get("title", ""),
                    "chapter": chapter_num,
                    "category": section.get("category", 0),
                }
            # Extract paragraph metadata from rubrics
            for cat_key, rubric_data in section.get("rubrics", {}).items():
                for para_id, para_text in rubric_data.get("paragraphs", {}).items():
                    paragraphs_metadata[para_id] = {
                        "text": para_text,
                        "section_fls_id": fls_id,
                        "section_title": section.get("title", ""),
                        "category": int(cat_key),
                        "chapter": chapter_num,
                    }
    
    return sections_metadata, paragraphs_metadata


def load_standard_data(root: Path, standard: str) -> dict:
    """Load extracted text for guideline lookup."""
    cache_path = get_standard_extracted_text_path(root, standard)
    if not cache_path.exists():
        print(f"ERROR: Extracted text not found: {cache_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(cache_path) as f:
        data = json.load(f)
    
    # Build lookup by guideline ID
    return {g["guideline_id"]: g for g in data.get("guidelines", [])}


def load_concept_to_fls(root: Path) -> dict:
    """Load concept to FLS mapping."""
    concept_path = get_concept_to_fls_path(root)
    if not concept_path.exists():
        return {}
    
    with open(concept_path) as f:
        data = json.load(f)
    
    return data.get("concepts", {})


def load_precomputed_similarity(root: Path, standard: str) -> dict:
    """Load pre-computed similarity results for see_also lookups."""
    sim_path = get_standard_similarity_path(root, standard)
    if not sim_path.exists():
        return {}
    
    with open(sim_path) as f:
        data = json.load(f)
    
    return data.get("results", {})


def load_add6_data(root: Path, guideline_id: str) -> dict | None:
    """Load ADD-6 data for a specific guideline."""
    add6_path = get_misra_rust_applicability_path(root)
    if not add6_path.exists():
        return None
    
    with open(add6_path) as f:
        data = json.load(f)
    
    guidelines = data.get("guidelines", {})
    return guidelines.get(guideline_id)


def format_rationale_codes(codes: list[str]) -> str:
    """Format rationale codes with full names."""
    if not codes:
        return "N/A"
    parts = []
    for code in codes:
        full_name = RATIONALE_CODE_NAMES.get(code)
        if full_name:
            parts.append(f"{code} ({full_name})")
        else:
            parts.append(code)
    return ", ".join(parts)


def search_fls(
    query_embedding: np.ndarray,
    fls_ids: list[str],
    fls_embeddings: np.ndarray,
    top_n: int = 20,
) -> list[tuple[str, float]]:
    """
    Search FLS embeddings with a query embedding.
    
    Returns list of (fls_id, similarity_score) tuples, sorted by score descending.
    """
    if len(fls_ids) == 0 or fls_embeddings.size == 0:
        return []
    
    # Compute cosine similarity
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    embed_norms = fls_embeddings / np.linalg.norm(fls_embeddings, axis=1, keepdims=True)
    similarities = np.dot(embed_norms, query_norm)
    
    # Get top-n indices
    top_indices = np.argsort(similarities)[::-1][:top_n]
    
    results = []
    for idx in top_indices:
        fls_id = fls_ids[idx]
        score = float(similarities[idx])
        results.append((fls_id, score))
    
    return results


def get_guideline_embeddings(
    guideline_id: str,
    root: Path,
    standard: str,
) -> list[tuple[str, np.ndarray, str]]:
    """
    Get all embeddings for a specific guideline.
    
    Returns list of (embedding_id, embedding_vector, source_type) tuples.
    """
    result = []
    
    # 1. Guideline-level embedding
    ids, embeds, id_to_idx, _ = load_embeddings(get_standard_embeddings_path(root, standard))
    if guideline_id in id_to_idx:
        idx = id_to_idx[guideline_id]
        result.append((guideline_id, embeds[idx], "guideline"))
    
    # 2. Query-level embeddings
    ids, embeds, id_to_idx, metadata = load_embeddings(get_standard_query_embeddings_path(root, standard))
    for qid, meta in metadata.items():
        if meta.get("guideline_id") == guideline_id:
            if qid in id_to_idx:
                idx = id_to_idx[qid]
                result.append((qid, embeds[idx], "query"))
    
    # 3. Rationale-level embedding
    rationale_id = f"{guideline_id}.rationale"
    ids, embeds, id_to_idx, _ = load_embeddings(get_standard_rationale_embeddings_path(root, standard))
    if rationale_id in id_to_idx:
        idx = id_to_idx[rationale_id]
        result.append((rationale_id, embeds[idx], "rationale"))
    
    # 4. Amplification-level embedding
    amp_id = f"{guideline_id}.amplification"
    ids, embeds, id_to_idx, _ = load_embeddings(get_standard_amplification_embeddings_path(root, standard))
    if amp_id in id_to_idx:
        idx = id_to_idx[amp_id]
        result.append((amp_id, embeds[idx], "amplification"))
    
    return result


def merge_results(
    all_results: list[dict],
    result_type: str,
) -> list[dict]:
    """
    Merge results from multiple searches, keeping highest score per FLS ID.
    
    Args:
        all_results: List of result dicts with 'fls_id', 'score', 'sources', etc.
        result_type: 'section' or 'paragraph'
    
    Returns:
        Merged and deduplicated results, sorted by score descending.
    """
    merged = {}
    
    for result in all_results:
        fls_id = result["fls_id"]
        score = result["score"]
        source = result.get("source", "unknown")
        
        if fls_id not in merged:
            merged[fls_id] = {
                **result,
                "sources": [source],
                "max_score": score,
            }
        else:
            # Keep highest score
            if score > merged[fls_id]["max_score"]:
                merged[fls_id]["max_score"] = score
                merged[fls_id]["score"] = score
            # Track all sources
            if source not in merged[fls_id]["sources"]:
                merged[fls_id]["sources"].append(source)
    
    # Sort by score
    results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    
    return results


def apply_concept_boost(
    results: list[dict],
    matched_concepts: list[str],
    concept_to_fls: dict,
) -> list[dict]:
    """
    Apply concept boost to results.
    
    - Adds CONCEPT_BOOST_ADDITIVE to score for FLS IDs in matched concepts
    - Adds FLS IDs from concepts that weren't in results with CONCEPT_ONLY_BASE_SCORE
    """
    if not matched_concepts or not concept_to_fls:
        return results
    
    # Collect all boosted FLS IDs from matched concepts
    boosted_fls_ids = {}
    for concept_name in matched_concepts:
        concept = concept_to_fls.get(concept_name, {})
        for fls_id in concept.get("fls_ids", []):
            if fls_id not in boosted_fls_ids:
                boosted_fls_ids[fls_id] = []
            boosted_fls_ids[fls_id].append(concept_name)
    
    # Track which FLS IDs are already in results
    result_fls_ids = {r["fls_id"] for r in results}
    
    # Apply boost to existing results
    for result in results:
        fls_id = result["fls_id"]
        if fls_id in boosted_fls_ids:
            result["original_score"] = result["score"]
            result["score"] = min(1.0, result["score"] + CONCEPT_BOOST_ADDITIVE)
            result["concept_boost"] = True
            result["boost_concepts"] = boosted_fls_ids[fls_id]
    
    # Add concept-only matches (not found by embedding search)
    for fls_id, concepts in boosted_fls_ids.items():
        if fls_id not in result_fls_ids:
            results.append({
                "fls_id": fls_id,
                "score": CONCEPT_ONLY_BASE_SCORE,
                "sources": ["concept_only"],
                "concept_boost": True,
                "boost_concepts": concepts,
            })
    
    # Re-sort by score
    results.sort(key=lambda x: x["score"], reverse=True)
    
    return results


def apply_see_also(
    results: list[dict],
    see_also_refs: list[str],
    precomputed: dict,
    result_type: str,
) -> list[dict]:
    """
    Add matches from see_also referenced guidelines.
    """
    if not see_also_refs or not precomputed:
        return results
    
    result_fls_ids = {r["fls_id"] for r in results}
    
    for ref_id in see_also_refs:
        ref_data = precomputed.get(ref_id, {})
        
        # Get top matches from referenced guideline
        if result_type == "section":
            ref_matches = ref_data.get("top_matches", [])[:SEE_ALSO_MAX_MATCHES]
        else:
            ref_matches = ref_data.get("top_paragraph_matches", [])[:SEE_ALSO_MAX_MATCHES]
        
        for match in ref_matches:
            fls_id = match.get("fls_id")
            if not fls_id:
                continue
            
            original_score = match.get("similarity", 0)
            adjusted_score = original_score * SEE_ALSO_SCORE_PENALTY
            
            if fls_id in result_fls_ids:
                # Already in results - just note the reference
                for r in results:
                    if r["fls_id"] == fls_id:
                        if "via_see_also" not in r:
                            r["via_see_also"] = []
                        r["via_see_also"].append(ref_id)
                        break
            else:
                # Add new result from see_also
                results.append({
                    "fls_id": fls_id,
                    "score": adjusted_score,
                    "original_score": original_score,
                    "sources": ["see_also"],
                    "via_see_also": [ref_id],
                    "title": match.get("title", ""),
                    "category": match.get("category", 0),
                })
                result_fls_ids.add(fls_id)
    
    # Re-sort by score
    results.sort(key=lambda x: x["score"], reverse=True)
    
    return results


def deep_search(
    guideline_id: str,
    root: Path,
    standard: str,
    top_n: int = 15,
    use_concept_boost: bool = True,
    use_see_also: bool = True,
    include_add6: bool = True,
) -> dict:
    """
    Perform deep search for a guideline using all embedding types.
    
    Returns dict with:
    - guideline_id
    - embeddings_used: List of embedding IDs used
    - per_embedding_results: Results from each embedding
    - merged_section_results: Merged section-level results
    - merged_paragraph_results: Merged paragraph-level results
    - concept_boosts: Concepts that were applied
    - see_also_refs: Referenced guidelines used
    """
    # Load FLS embeddings
    section_ids, section_embeds, _, _ = load_embeddings(get_fls_section_embeddings_path(root))
    para_ids, para_embeds, _, _ = load_embeddings(get_fls_paragraph_embeddings_path(root))
    
    # Load FLS metadata
    chapters = load_fls_chapters(root)
    sections_meta, paragraphs_meta = build_fls_metadata(chapters)
    
    # Load standard data
    standard_data = load_standard_data(root, standard)
    guideline = standard_data.get(guideline_id)
    
    if not guideline:
        return {"error": f"Guideline '{guideline_id}' not found"}
    
    # Get all embeddings for this guideline
    guideline_embeddings = get_guideline_embeddings(guideline_id, root, standard)
    
    if not guideline_embeddings:
        return {"error": f"No embeddings found for '{guideline_id}'"}
    
    # Search with each embedding
    per_embedding_results = {}
    all_section_results = []
    all_paragraph_results = []
    
    for embed_id, embed_vec, source_type in guideline_embeddings:
        # Search sections
        section_hits = search_fls(embed_vec, section_ids, section_embeds, top_n)
        section_results = []
        for fls_id, score in section_hits:
            meta = sections_meta.get(fls_id, {})
            result = {
                "fls_id": fls_id,
                "score": score,
                "source": embed_id,
                "title": meta.get("title", ""),
                "chapter": meta.get("chapter"),
                "category": meta.get("category", 0),
                "type": "section",
            }
            section_results.append(result)
            all_section_results.append(result.copy())
        
        # Search paragraphs
        para_hits = search_fls(embed_vec, para_ids, para_embeds, top_n)
        para_results = []
        for fls_id, score in para_hits:
            meta = paragraphs_meta.get(fls_id, {})
            category = meta.get("category", 0)
            result = {
                "fls_id": fls_id,
                "score": score,
                "source": embed_id,
                "section_fls_id": meta.get("section_fls_id", ""),
                "section_title": meta.get("section_title", ""),
                "category": category,
                "category_name": CATEGORY_NAMES.get(category, f"unknown_{category}"),
                "text_preview": meta.get("text", "")[:150],
                "chapter": meta.get("chapter"),
                "type": "paragraph",
            }
            para_results.append(result)
            all_paragraph_results.append(result.copy())
        
        per_embedding_results[embed_id] = {
            "source_type": source_type,
            "sections": section_results,
            "paragraphs": para_results,
        }
    
    # Merge results
    merged_sections = merge_results(all_section_results, "section")
    merged_paragraphs = merge_results(all_paragraph_results, "paragraph")
    
    # Apply concept boost
    matched_concepts = guideline.get("matched_concepts", [])
    concept_boosts_applied = []
    
    if use_concept_boost and matched_concepts:
        concept_to_fls = load_concept_to_fls(root)
        merged_sections = apply_concept_boost(merged_sections, matched_concepts, concept_to_fls)
        merged_paragraphs = apply_concept_boost(merged_paragraphs, matched_concepts, concept_to_fls)
        concept_boosts_applied = matched_concepts
    
    # Apply see_also
    see_also_refs = guideline.get("see_also_refs", [])
    
    if use_see_also and see_also_refs:
        precomputed = load_precomputed_similarity(root, standard)
        merged_sections = apply_see_also(merged_sections, see_also_refs, precomputed, "section")
        merged_paragraphs = apply_see_also(merged_paragraphs, see_also_refs, precomputed, "paragraph")
    
    # Load ADD-6 data if requested
    add6_data = None
    if include_add6:
        add6_data = load_add6_data(root, guideline_id)
    
    return {
        "guideline_id": guideline_id,
        "guideline_title": guideline.get("title", "").split("\n")[0][:100],
        "misra_add6": add6_data,
        "embeddings_used": [e[0] for e in guideline_embeddings],
        "embedding_sources": {e[0]: e[2] for e in guideline_embeddings},
        "per_embedding_results": per_embedding_results,
        "merged_section_results": merged_sections,
        "merged_paragraph_results": merged_paragraphs,
        "concept_boosts_applied": concept_boosts_applied,
        "see_also_refs_used": see_also_refs if use_see_also else [],
    }


def format_results(results: dict, mode: str, top_n: int, show_add6: bool = True) -> None:
    """Format and print results."""
    if "error" in results:
        print(f"ERROR: {results['error']}")
        return
    
    print(f"\n{'='*70}")
    print(f"DEEP SEARCH RESULTS: {results['guideline_id']}")
    print(f"{'='*70}")
    print(f"Title: {results['guideline_title']}")
    
    # Display ADD-6 context if available and not suppressed
    add6 = results.get("misra_add6")
    if show_add6 and add6:
        print(f"\nMISRA ADD-6 Context:")
        print(f"  Original Category: {add6.get('misra_category', 'N/A')}")
        print(f"  Decidability: {add6.get('decidability', 'N/A')}")
        print(f"  Scope: {add6.get('scope', 'N/A')}")
        rationale = format_rationale_codes(add6.get("rationale", []))
        print(f"  Rationale: {rationale}")
        all_rust = add6.get("applicability_all_rust", "N/A")
        safe_rust = add6.get("applicability_safe_rust", "N/A")
        adjusted = add6.get("adjusted_category", "N/A")
        print(f"  All Rust: {all_rust} → {adjusted}")
        print(f"  Safe Rust: {safe_rust}")
        if add6.get("comment"):
            print(f"  Comment: {add6.get('comment')}")
    
    print(f"\nEmbeddings used: {len(results['embeddings_used'])}")
    for eid in results['embeddings_used']:
        source = results['embedding_sources'].get(eid, "unknown")
        print(f"  - {eid} ({source})")
    
    if results.get("concept_boosts_applied"):
        print(f"\nConcept boosts: {', '.join(results['concept_boosts_applied'][:5])}")
        if len(results['concept_boosts_applied']) > 5:
            print(f"  ... and {len(results['concept_boosts_applied']) - 5} more")
    
    if results.get("see_also_refs_used"):
        print(f"See-also refs: {', '.join(results['see_also_refs_used'])}")
    
    # Section results
    print(f"\n--- TOP SECTION MATCHES ({len(results['merged_section_results'])} total) ---")
    for i, r in enumerate(results['merged_section_results'][:top_n], 1):
        boost_marker = " [CONCEPT]" if r.get("concept_boost") else ""
        see_also_marker = f" [via {r['via_see_also'][0]}]" if r.get("via_see_also") else ""
        sources = ", ".join(r.get("sources", [])[:2])
        print(f"{i:2}. [{r['score']:.3f}] {r['fls_id']}: {r.get('title', '')[:50]}{boost_marker}{see_also_marker}")
        if mode == "detailed":
            print(f"      Sources: {sources}")
    
    # Paragraph results
    print(f"\n--- TOP PARAGRAPH MATCHES ({len(results['merged_paragraph_results'])} total) ---")
    for i, r in enumerate(results['merged_paragraph_results'][:top_n], 1):
        boost_marker = " [CONCEPT]" if r.get("concept_boost") else ""
        cat_name = r.get("category_name", "")
        print(f"{i:2}. [{r['score']:.3f}] {r['fls_id']} [{cat_name}]{boost_marker}")
        print(f"      Section: {r.get('section_title', '')[:50]}")
        if mode == "detailed":
            preview = r.get("text_preview", "")[:80]
            print(f"      Text: {preview}...")
            sources = ", ".join(r.get("sources", [])[:2])
            print(f"      Sources: {sources}")


def main():
    parser = argparse.ArgumentParser(
        description="Deep semantic search across FLS for a coding standard guideline"
    )
    parser.add_argument(
        "--standard",
        type=str,
        required=True,
        choices=VALID_STANDARDS,
        help="Coding standard (e.g., misra-c, cert-cpp)",
    )
    parser.add_argument(
        "--guideline",
        type=str,
        required=True,
        help="Guideline ID (e.g., 'Rule 21.3')",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of top results per embedding (default: 15)",
    )
    parser.add_argument(
        "--mode",
        choices=["merged", "detailed"],
        default="merged",
        help="Output mode: 'merged' (default) or 'detailed'",
    )
    parser.add_argument(
        "--no-concept-boost",
        action="store_true",
        help="Disable concept boost",
    )
    parser.add_argument(
        "--no-see-also",
        action="store_true",
        help="Disable see-also integration",
    )
    parser.add_argument(
        "--no-add6",
        action="store_true",
        help="Suppress MISRA ADD-6 context display",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Generate and print search ID for verification workflow tracking
    search_id = generate_search_id()
    print(f"Search ID: {search_id}")
    print()
    
    print(f"Performing deep search for: {args.guideline}", file=sys.stderr)
    
    results = deep_search(
        args.guideline,
        root,
        args.standard,
        top_n=args.top,
        use_concept_boost=not args.no_concept_boost,
        use_see_also=not args.no_see_also,
        include_add6=not args.no_add6,
    )
    
    if args.json:
        # Clean up numpy types for JSON serialization
        def clean_for_json(obj):
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_for_json(v) for v in obj]
            elif isinstance(obj, (np.integer, np.floating)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj
        
        print(json.dumps(clean_for_json(results), indent=2))
    else:
        format_results(results, args.mode, args.top, show_add6=not args.no_add6)
    
    # Summary stats
    if not args.json:
        print(f"\nFound {len(results.get('merged_section_results', []))} section matches, "
              f"{len(results.get('merged_paragraph_results', []))} paragraph matches.", 
              file=sys.stderr)


if __name__ == "__main__":
    main()
