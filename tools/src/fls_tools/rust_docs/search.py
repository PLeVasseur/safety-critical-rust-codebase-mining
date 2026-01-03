#!/usr/bin/env python3
"""
search-rust-context: Semantic search across Rust documentation.

Searches embeddings from:
- Rust Reference
- Unsafe Code Guidelines (UCG)
- Rustonomicon
- Clippy lints

This tool complements search-fls by providing broader Rust context
before searching the FLS specification.

Usage:
    uv run search-rust-context --query "memory allocation" --top 10
    uv run search-rust-context --query "pointer safety" --source reference
    uv run search-rust-context --query "unsafe transmute" --source clippy

Options:
    --query TEXT        Search query text
    --top N             Number of results per source (default: 5)
    --source SOURCE     Search only one source (reference/ucg/nomicon/clippy)
    --verbose           Show full content snippets
    --json              Output results as JSON
"""

import argparse
import json
import pickle
import sys
import uuid
from pathlib import Path

import numpy as np

from fls_tools.shared import get_project_root, get_embeddings_dir


# Default sources to search (in order of priority)
DEFAULT_SOURCES = ["reference", "ucg", "nomicon", "clippy"]


def generate_search_id() -> str:
    """Generate a unique ID for this search execution."""
    return str(uuid.uuid4())


def load_embeddings(embeddings_path: Path) -> dict | None:
    """
    Load embeddings from pickle file.
    
    Returns dict with ids, embeddings, id_to_index, and optional metadata.
    """
    if not embeddings_path.exists():
        return None
    
    with open(embeddings_path, "rb") as f:
        data = pickle.load(f)
    
    return data


def load_chapter_data(source_dir: Path) -> dict:
    """Load chapter data for content lookup."""
    chapters = {}
    
    for chapter_file in source_dir.glob("chapter_*.json"):
        try:
            with open(chapter_file) as f:
                data = json.load(f)
            chapters[chapter_file.stem] = data
        except (json.JSONDecodeError, KeyError):
            continue
    
    return chapters


def load_clippy_lints(source_dir: Path) -> dict:
    """Load Clippy lints for content lookup."""
    lints_path = source_dir / "lints.json"
    if not lints_path.exists():
        return {}
    
    with open(lints_path) as f:
        data = json.load(f)
    
    # Index by lint ID
    return {lint["id"]: lint for lint in data.get("lints", [])}


def cosine_similarity_batch(query: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity between query and all embeddings."""
    query_norm = query / np.linalg.norm(query)
    embed_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    return np.dot(embed_norms, query_norm)


def search_source(
    query_embedding: np.ndarray,
    source_name: str,
    embeddings_dir: Path,
    top_n: int,
    search_paragraphs: bool = True,
) -> list[dict]:
    """
    Search a single documentation source.
    
    Returns list of results with similarity scores.
    """
    source_dir = embeddings_dir / source_name
    results = []
    
    # Load section embeddings
    section_data = load_embeddings(source_dir / "embeddings.pkl")
    if section_data is None:
        return []
    
    ids = section_data.get("ids", [])
    embeddings = section_data.get("embeddings", np.array([]))
    
    if len(ids) == 0 or embeddings.size == 0:
        return []
    
    # Compute similarities
    similarities = cosine_similarity_batch(query_embedding, embeddings)
    top_indices = np.argsort(similarities)[::-1][:top_n]
    
    # Get chapter data for content lookup
    if source_name == "clippy":
        lints = load_clippy_lints(source_dir)
        category_weights = section_data.get("category_weights", {})
    else:
        chapters = load_chapter_data(source_dir)
    
    for idx in top_indices:
        item_id = ids[idx]
        similarity = float(similarities[idx])
        
        result = {
            "source": source_name,
            "id": item_id,
            "similarity": similarity,
            "type": "section",
        }
        
        if source_name == "clippy":
            lint = lints.get(item_id, {})
            result["title"] = lint.get("snake_name", item_id)
            result["category"] = lint.get("category", "")
            result["brief"] = lint.get("brief", "")
            result["content"] = lint.get("what_it_does", "")
            
            # Apply category weight for weighted score
            weight = category_weights.get(lint.get("category", ""), 1.0)
            result["weighted_similarity"] = similarity * weight
        else:
            # For mdBook sources, find content in chapters
            result["title"] = item_id
            result["content"] = ""
            for chapter_data in chapters.values():
                for section in chapter_data.get("sections", []):
                    if section.get("id") == item_id:
                        result["title"] = section.get("title", item_id)
                        result["content"] = section.get("content", "")[:500]
                        result["chapter"] = chapter_data.get("title", "")
                        break
        
        results.append(result)
    
    # Also search paragraphs if available and requested
    if search_paragraphs and source_name != "clippy":
        para_data = load_embeddings(source_dir / "paragraph_embeddings.pkl")
        if para_data is not None:
            para_ids = para_data.get("ids", [])
            para_embeddings = para_data.get("embeddings", np.array([]))
            para_metadata = para_data.get("metadata", {})
            
            if len(para_ids) > 0 and para_embeddings.size > 0:
                para_similarities = cosine_similarity_batch(query_embedding, para_embeddings)
                top_para_indices = np.argsort(para_similarities)[::-1][:top_n]
                
                for idx in top_para_indices:
                    para_id = para_ids[idx]
                    similarity = float(para_similarities[idx])
                    meta = para_metadata.get(para_id, {})
                    
                    results.append({
                        "source": source_name,
                        "id": para_id,
                        "similarity": similarity,
                        "type": "paragraph",
                        "title": meta.get("section_title", ""),
                        "chapter": meta.get("chapter_title", ""),
                        "content": meta.get("text", "")[:300],
                    })
    
    return results


def format_results(results: list[dict], verbose: bool) -> None:
    """Format and print search results."""
    if not results:
        print("No results found.")
        return
    
    # Group by source
    by_source: dict[str, list[dict]] = {}
    for r in results:
        source = r["source"]
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(r)
    
    # Print each source's results
    for source in DEFAULT_SOURCES:
        if source not in by_source:
            continue
        
        source_results = by_source[source]
        source_display = {
            "reference": "Rust Reference",
            "ucg": "Unsafe Code Guidelines",
            "nomicon": "Rustonomicon",
            "clippy": "Clippy Lints",
        }.get(source, source.title())
        
        print(f"\n{'='*60}")
        print(f" {source_display}")
        print(f"{'='*60}")
        
        for i, r in enumerate(source_results, 1):
            if source == "clippy":
                score_str = f"{r['similarity']:.3f}"
                if "weighted_similarity" in r:
                    score_str += f" (w:{r['weighted_similarity']:.3f})"
                print(f"\n{i}. [{score_str}] {r['id']}")
                print(f"   Category: {r.get('category', 'N/A')}")
                print(f"   Brief: {r.get('brief', 'N/A')}")
                if verbose and r.get("content"):
                    content = r["content"][:300]
                    if len(r.get("content", "")) > 300:
                        content += "..."
                    print(f"   Content: {content}")
            else:
                type_indicator = "[§]" if r["type"] == "section" else "[¶]"
                print(f"\n{i}. [{r['similarity']:.3f}] {type_indicator} {r['id']}")
                print(f"   Title: {r.get('title', 'N/A')}")
                if r.get("chapter"):
                    print(f"   Chapter: {r['chapter']}")
                if verbose and r.get("content"):
                    content = r["content"][:300]
                    if len(r.get("content", "")) > 300:
                        content += "..."
                    print(f"   Content: {content}")


def main():
    parser = argparse.ArgumentParser(
        description="Semantic search across Rust documentation"
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Search query text",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of results per source (default: 5)",
    )
    parser.add_argument(
        "--source",
        choices=["reference", "ucg", "nomicon", "clippy", "all"],
        default="all",
        help="Search only specific source",
    )
    parser.add_argument(
        "--sections-only",
        action="store_true",
        help="Search only section-level embeddings (skip paragraphs)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show more content in results",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    root = get_project_root()
    embeddings_dir = get_embeddings_dir(root)
    
    # Generate and print search ID
    search_id = generate_search_id()
    if not args.json:
        print(f"Search ID: {search_id}")
        print(f"Query: {args.query}")
    
    # Load model
    if not args.json:
        print("\nLoading model...", file=sys.stderr)
    
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-mpnet-base-v2")
    
    # Generate query embedding
    query_embedding = model.encode(args.query)
    
    # Determine sources to search
    if args.source == "all":
        sources = DEFAULT_SOURCES
    else:
        sources = [args.source]
    
    # Search each source
    all_results = []
    for source in sources:
        if not args.json:
            print(f"Searching {source}...", file=sys.stderr)
        
        results = search_source(
            query_embedding,
            source,
            embeddings_dir,
            args.top,
            search_paragraphs=not args.sections_only,
        )
        all_results.extend(results)
    
    # Sort by similarity (descending)
    all_results.sort(key=lambda x: x.get("weighted_similarity", x["similarity"]), reverse=True)
    
    # Output
    if args.json:
        output = {
            "search_id": search_id,
            "query": args.query,
            "sources": sources,
            "top_n": args.top,
            "results": all_results,
        }
        print(json.dumps(output, indent=2))
    else:
        format_results(all_results, args.verbose)
        
        # Print summary
        total = len(all_results)
        print(f"\n{'='*60}")
        print(f"Total: {total} results from {len(sources)} source(s)")
    
    return 0


if __name__ == "__main__":
    exit(main())
