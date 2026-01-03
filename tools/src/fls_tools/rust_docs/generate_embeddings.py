#!/usr/bin/env python3
"""
generate-rust-embeddings: Generate embeddings for Rust documentation sources.

Generates vector embeddings for:
- Rust Reference (section + paragraph level)
- Unsafe Code Guidelines (section + paragraph level)
- Rustonomicon (section + paragraph level)
- Clippy lints (lint level with weighted categories)

These embeddings complement FLS embeddings for richer context search.

Usage:
    uv run generate-rust-embeddings              # Generate all embeddings
    uv run generate-rust-embeddings --force      # Regenerate even if exists
    uv run generate-rust-embeddings --source reference  # Single source

Options:
    --model MODEL       Embedding model (default: all-mpnet-base-v2)
    --source SOURCE     Generate for specific source only
    --force             Regenerate even if embeddings exist

Output:
    embeddings/reference/embeddings.pkl
    embeddings/reference/paragraph_embeddings.pkl
    embeddings/ucg/embeddings.pkl
    embeddings/ucg/paragraph_embeddings.pkl
    embeddings/nomicon/embeddings.pkl
    embeddings/nomicon/paragraph_embeddings.pkl
    embeddings/clippy/embeddings.pkl
"""

import argparse
import json
import pickle
from datetime import date
from pathlib import Path

import numpy as np


from fls_tools.shared import get_project_root, get_embeddings_dir


def load_index(source_dir: Path) -> dict:
    """Load index.json for a source."""
    index_path = source_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    with open(index_path, encoding="utf-8") as f:
        return json.load(f)


def load_chapters(source_dir: Path, index: dict) -> list[dict]:
    """Load all chapter files for a source."""
    chapters = []
    for chapter_info in index.get("chapters", []):
        chapter_path = source_dir / chapter_info["file"]
        if chapter_path.exists():
            with open(chapter_path, encoding="utf-8") as f:
                chapters.append(json.load(f))
    return chapters


def prepare_section_texts(chapters: list[dict], source_name: str) -> list[tuple[str, str]]:
    """
    Prepare section-level texts for embedding.
    
    Returns list of (section_id, text_to_embed).
    """
    texts = []
    
    for chapter in chapters:
        chapter_title = chapter.get("title", "")
        
        for section in chapter.get("sections", []):
            section_id = section.get("id", "")
            if not section_id:
                continue
            
            section_title = section.get("title", "")
            content = section.get("content", "")
            
            # Build text with context
            parts = [f"Chapter: {chapter_title}"]
            if section_title:
                parts.append(f"Section: {section_title}")
            
            # Truncate very long content
            if len(content) > 8000:
                content = content[:8000] + "..."
            if content:
                parts.append(content)
            
            text = "\n".join(parts)
            
            if len(text.strip()) >= 20:
                texts.append((section_id, text))
    
    return texts


def prepare_paragraph_texts(
    chapters: list[dict],
    source_name: str
) -> tuple[list[tuple[str, str]], dict]:
    """
    Prepare paragraph-level texts for embedding.
    
    Returns:
        Tuple of:
        - List of (para_id, text_to_embed) tuples
        - Dict of metadata: para_id -> {section_id, section_title, chapter_title}
    """
    texts = []
    metadata = {}
    
    for chapter in chapters:
        chapter_title = chapter.get("title", "")
        
        for section in chapter.get("sections", []):
            section_id = section.get("id", "")
            section_title = section.get("title", "")
            
            for para_id, para_text in section.get("paragraphs", {}).items():
                if not para_text or len(para_text.strip()) < 20:
                    continue
                
                # Build text with context for better semantic matching
                text = f"Chapter: {chapter_title}\nSection: {section_title}\n{para_text}"
                
                texts.append((para_id, text))
                
                metadata[para_id] = {
                    "section_id": section_id,
                    "section_title": section_title,
                    "chapter_title": chapter_title,
                    "text": para_text,
                }
    
    return texts, metadata


def prepare_clippy_texts(lints_data: dict) -> list[tuple[str, str]]:
    """
    Prepare Clippy lint texts for embedding.
    
    Returns list of (lint_id, text_to_embed).
    """
    texts = []
    
    for lint in lints_data.get("lints", []):
        lint_id = lint.get("id", "")  # clippy::lint_name format
        embedding_text = lint.get("embedding_text", "")
        
        if lint_id and embedding_text and len(embedding_text.strip()) >= 20:
            # Add category context
            category = lint.get("category", "")
            brief = lint.get("brief", "")
            
            text = f"Category: {category}\nBrief: {brief}\n\n{embedding_text}"
            texts.append((lint_id, text))
    
    return texts


def generate_embeddings(texts: list[tuple[str, str]], model) -> dict:
    """
    Generate embeddings for a list of (id, text) pairs.
    Returns dict with ids, embeddings array, and id_to_index lookup.
    """
    ids = [t[0] for t in texts]
    text_content = [t[1] for t in texts]
    
    print(f"  Generating embeddings for {len(texts)} items...")
    embeddings = model.encode(text_content, show_progress_bar=True)
    
    return {
        "ids": ids,
        "embeddings": embeddings,
        "id_to_index": {id_: i for i, id_ in enumerate(ids)},
    }


def process_mdbook_source(
    source_dir: Path,
    source_name: str,
    model,
    force: bool,
    model_name: str,
) -> None:
    """Process an mdBook-style source (Reference, UCG, Nomicon)."""
    print(f"\n{'='*60}")
    print(f"Processing: {source_name}")
    print(f"{'='*60}")
    
    # Check if already exists
    section_path = source_dir / "embeddings.pkl"
    para_path = source_dir / "paragraph_embeddings.pkl"
    
    if section_path.exists() and para_path.exists() and not force:
        print(f"  Embeddings exist. Use --force to regenerate.")
        return
    
    # Load data
    print("Loading data...")
    index = load_index(source_dir)
    chapters = load_chapters(source_dir, index)
    print(f"  Loaded {len(chapters)} chapters")
    
    # Section-level embeddings
    print("\nPreparing section-level texts...")
    section_texts = prepare_section_texts(chapters, source_name)
    print(f"  Prepared {len(section_texts)} sections")
    
    if section_texts:
        section_embeddings = generate_embeddings(section_texts, model)
        with open(section_path, "wb") as f:
            pickle.dump({
                "model": model_name,
                "generated_date": str(date.today()),
                "source": source_name,
                "count": len(section_texts),
                **section_embeddings,
            }, f)
        print(f"  Saved: {section_path}")
    
    # Paragraph-level embeddings
    print("\nPreparing paragraph-level texts...")
    para_texts, para_metadata = prepare_paragraph_texts(chapters, source_name)
    print(f"  Prepared {len(para_texts)} paragraphs")
    
    if para_texts:
        para_embeddings = generate_embeddings(para_texts, model)
        with open(para_path, "wb") as f:
            pickle.dump({
                "model": model_name,
                "generated_date": str(date.today()),
                "source": source_name,
                "count": len(para_texts),
                "metadata": para_metadata,
                **para_embeddings,
            }, f)
        print(f"  Saved: {para_path}")


def process_clippy(
    clippy_dir: Path,
    model,
    force: bool,
    model_name: str,
) -> None:
    """Process Clippy lints."""
    print(f"\n{'='*60}")
    print("Processing: Clippy")
    print(f"{'='*60}")
    
    embeddings_path = clippy_dir / "embeddings.pkl"
    
    if embeddings_path.exists() and not force:
        print(f"  Embeddings exist. Use --force to regenerate.")
        return
    
    # Load lints
    lints_path = clippy_dir / "lints.json"
    if not lints_path.exists():
        print(f"  ERROR: {lints_path} not found")
        print("  Run: uv run extract-clippy-lints")
        return
    
    print("Loading lints...")
    with open(lints_path, encoding="utf-8") as f:
        lints_data = json.load(f)
    print(f"  Loaded {lints_data.get('total_lints', 0)} lints")
    
    # Prepare texts
    print("\nPreparing lint texts...")
    lint_texts = prepare_clippy_texts(lints_data)
    print(f"  Prepared {len(lint_texts)} lint embeddings")
    
    if lint_texts:
        embeddings = generate_embeddings(lint_texts, model)
        
        # Store category weights for weighted search
        category_weights = lints_data.get("category_weights", {})
        lint_categories = {
            lint["id"]: lint.get("category", "")
            for lint in lints_data.get("lints", [])
        }
        
        with open(embeddings_path, "wb") as f:
            pickle.dump({
                "model": model_name,
                "generated_date": str(date.today()),
                "source": "Clippy",
                "count": len(lint_texts),
                "category_weights": category_weights,
                "lint_categories": lint_categories,
                **embeddings,
            }, f)
        print(f"  Saved: {embeddings_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate embeddings for Rust documentation"
    )
    parser.add_argument(
        "--model",
        default="all-mpnet-base-v2",
        help="Sentence transformer model name",
    )
    parser.add_argument(
        "--source",
        choices=["reference", "ucg", "nomicon", "clippy", "all"],
        default="all",
        help="Generate for specific source only",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Regenerate even if exists",
    )
    
    args = parser.parse_args()
    root = get_project_root()
    embeddings_dir = get_embeddings_dir(root)
    
    # Load model
    print(f"Loading model: {args.model}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    print(f"  Embedding dimension: {model.get_sentence_embedding_dimension()}")
    
    sources_to_process = []
    if args.source == "all":
        sources_to_process = ["reference", "ucg", "nomicon", "clippy"]
    else:
        sources_to_process = [args.source]
    
    # Process each source
    for source in sources_to_process:
        if source == "clippy":
            process_clippy(
                embeddings_dir / "clippy",
                model,
                args.force,
                args.model,
            )
        else:
            process_mdbook_source(
                embeddings_dir / source,
                source.title() if source != "ucg" else "UCG",
                model,
                args.force,
                args.model,
            )
    
    # Summary
    print(f"\n{'='*60}")
    print("EMBEDDING GENERATION COMPLETE")
    print(f"{'='*60}")
    
    for source in sources_to_process:
        source_dir = embeddings_dir / source
        section_path = source_dir / "embeddings.pkl"
        para_path = source_dir / "paragraph_embeddings.pkl"
        
        if section_path.exists():
            with open(section_path, "rb") as f:
                data = pickle.load(f)
            print(f"{source}: {data.get('count', 0)} section embeddings")
        
        if para_path.exists():
            with open(para_path, "rb") as f:
                data = pickle.load(f)
            print(f"{source}: {data.get('count', 0)} paragraph embeddings")
    
    return 0


if __name__ == "__main__":
    exit(main())
