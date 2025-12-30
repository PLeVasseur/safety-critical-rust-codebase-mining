#!/usr/bin/env python3
"""
Generate vector embeddings for MISRA C and FLS content.

This script uses sentence-transformers to create semantic embeddings that
enable similarity search between MISRA guidelines and FLS sections.

Usage:
    uv run python tools/embeddings/generate_embeddings.py [--model MODEL]

Options:
    --model MODEL    Embedding model name (default: all-mpnet-base-v2)

Output:
    embeddings/misra_c/embeddings.pkl
    embeddings/fls/embeddings.pkl
"""

import argparse
import json
import pickle
from datetime import date
from pathlib import Path

import numpy as np


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def load_misra_text(project_root: Path) -> list[dict]:
    """Load MISRA extracted text from cache."""
    cache_path = project_root / "cache" / "misra_c_extracted_text.json"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"MISRA text not found at {cache_path}. "
            "Run extract_misra_text.py first."
        )
    with open(cache_path, encoding='utf-8') as f:
        data = json.load(f)
    return data['guidelines']


def load_fls_sections(project_root: Path) -> list[dict]:
    """Load FLS sections from embeddings directory."""
    sections_path = project_root / "embeddings" / "fls" / "sections.json"
    if not sections_path.exists():
        raise FileNotFoundError(
            f"FLS sections not found at {sections_path}. "
            "Run extract_fls_content.py first."
        )
    with open(sections_path, encoding='utf-8') as f:
        data = json.load(f)
    return data['sections']


def prepare_misra_texts(guidelines: list[dict]) -> list[tuple[str, str]]:
    """
    Prepare MISRA guidelines for embedding.
    Returns list of (guideline_id, text_to_embed).
    """
    texts = []
    for g in guidelines:
        gid = g['guideline_id']
        
        # Build comprehensive text for embedding
        parts = []
        
        # Title is important
        if g.get('title'):
            parts.append(f"Title: {g['title']}")
        
        # Rationale captures the intent
        if g.get('rationale'):
            parts.append(f"Rationale: {g['rationale']}")
        
        # Amplification provides details
        if g.get('amplification'):
            parts.append(f"Amplification: {g['amplification']}")
        
        # Category context
        if g.get('category'):
            parts.append(f"Category: {g['category']}")
        
        # If no specific parts, use full text
        if not parts and g.get('full_text'):
            parts.append(g['full_text'])
        
        text = '\n'.join(parts)
        
        # Skip if no meaningful text
        if len(text.strip()) < 20:
            text = g.get('title', gid)  # Fallback to title or ID
        
        texts.append((gid, text))
    
    return texts


def prepare_fls_texts(sections: list[dict]) -> list[tuple[str, str]]:
    """
    Prepare FLS sections for embedding.
    Returns list of (fls_id, text_to_embed).
    """
    texts = []
    for s in sections:
        fls_id = s['fls_id']
        
        # Build text for embedding
        parts = []
        
        # Title
        if s.get('title'):
            parts.append(f"Title: {s['title']}")
        
        # Content
        if s.get('content'):
            # Truncate very long content
            content = s['content']
            if len(content) > 8000:
                content = content[:8000] + "..."
            parts.append(content)
        
        text = '\n'.join(parts)
        
        # Skip if no meaningful text
        if len(text.strip()) < 20:
            text = s.get('title', fls_id)
        
        texts.append((fls_id, text))
    
    return texts


def generate_embeddings(texts: list[tuple[str, str]], model) -> dict:
    """
    Generate embeddings for a list of (id, text) pairs.
    Returns dict mapping id -> embedding vector.
    """
    ids = [t[0] for t in texts]
    text_content = [t[1] for t in texts]
    
    print(f"  Generating embeddings for {len(texts)} items...")
    embeddings = model.encode(text_content, show_progress_bar=True)
    
    # Convert to dict
    result = {
        'ids': ids,
        'embeddings': embeddings,
        'id_to_index': {id_: i for i, id_ in enumerate(ids)}
    }
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Generate embeddings for MISRA and FLS')
    parser.add_argument('--model', default='all-mpnet-base-v2',
                       help='Sentence transformer model name')
    args = parser.parse_args()
    
    project_root = get_project_root()
    
    # Load sentence transformer model
    print(f"Loading model: {args.model}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    print(f"  Model loaded. Embedding dimension: {model.get_sentence_embedding_dimension()}")
    
    # Load and prepare MISRA text
    print("\nLoading MISRA guidelines...")
    guidelines = load_misra_text(project_root)
    print(f"  Loaded {len(guidelines)} guidelines")
    
    misra_texts = prepare_misra_texts(guidelines)
    print(f"  Prepared {len(misra_texts)} texts for embedding")
    
    # Generate MISRA embeddings
    print("\nGenerating MISRA embeddings...")
    misra_embeddings = generate_embeddings(misra_texts, model)
    
    # Save MISRA embeddings
    misra_output = project_root / "embeddings" / "misra_c" / "embeddings.pkl"
    misra_output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(misra_output, 'wb') as f:
        pickle.dump({
            'model': args.model,
            'generated_date': str(date.today()),
            'num_items': len(misra_embeddings['ids']),
            'embedding_dim': model.get_sentence_embedding_dimension(),
            'data': misra_embeddings
        }, f)
    print(f"  Saved to: {misra_output}")
    print(f"  File size: {misra_output.stat().st_size / 1024 / 1024:.2f} MB")
    
    # Load and prepare FLS sections
    print("\nLoading FLS sections...")
    sections = load_fls_sections(project_root)
    print(f"  Loaded {len(sections)} sections")
    
    fls_texts = prepare_fls_texts(sections)
    print(f"  Prepared {len(fls_texts)} texts for embedding")
    
    # Generate FLS embeddings
    print("\nGenerating FLS embeddings...")
    fls_embeddings = generate_embeddings(fls_texts, model)
    
    # Save FLS embeddings
    fls_output = project_root / "embeddings" / "fls" / "embeddings.pkl"
    fls_output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(fls_output, 'wb') as f:
        pickle.dump({
            'model': args.model,
            'generated_date': str(date.today()),
            'num_items': len(fls_embeddings['ids']),
            'embedding_dim': model.get_sentence_embedding_dimension(),
            'data': fls_embeddings
        }, f)
    print(f"  Saved to: {fls_output}")
    print(f"  File size: {fls_output.stat().st_size / 1024 / 1024:.2f} MB")
    
    print("\nDone!")
    return 0


if __name__ == "__main__":
    exit(main())
