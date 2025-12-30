#!/usr/bin/env python3
"""
Compute similarity between MISRA guidelines and FLS sections.

This script:
1. Loads pre-computed embeddings for MISRA and FLS
2. Computes cosine similarity matrix
3. For each MISRA guideline, finds top-N most similar FLS sections
4. Identifies "missing siblings" when partial section matches occur
5. Saves results for use in verification

Usage:
    uv run python tools/embeddings/compute_similarity.py [--top-n N]

Options:
    --top-n N    Number of top similar FLS sections to return (default: 20)

Output:
    embeddings/similarity/misra_c_to_fls.json
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


def load_embeddings(path: Path) -> dict:
    """Load embeddings from pickle file."""
    with open(path, 'rb') as f:
        return pickle.load(f)


def load_fls_sections(project_root: Path) -> dict:
    """Load FLS sections metadata for sibling detection."""
    path = project_root / "embeddings" / "fls" / "sections.json"
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    
    # Build lookup by FLS ID
    sections_by_id = {s['fls_id']: s for s in data['sections']}
    return sections_by_id


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between two sets of vectors.
    a: (m, d) matrix
    b: (n, d) matrix
    Returns: (m, n) similarity matrix
    """
    # Normalize vectors
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    
    # Compute dot product
    return np.dot(a_norm, b_norm.T)


def find_top_similar(similarity_matrix: np.ndarray, 
                     misra_ids: list[str],
                     fls_ids: list[str],
                     top_n: int = 20) -> dict:
    """
    Find top-N most similar FLS sections for each MISRA guideline.
    Returns dict mapping misra_id -> list of (fls_id, similarity_score).
    """
    results = {}
    
    for i, misra_id in enumerate(misra_ids):
        # Get similarities for this MISRA guideline
        sims = similarity_matrix[i]
        
        # Get top-N indices
        top_indices = np.argsort(sims)[::-1][:top_n]
        
        # Build result list
        top_matches = []
        for idx in top_indices:
            fls_id = fls_ids[idx]
            score = float(sims[idx])
            top_matches.append({
                'fls_id': fls_id,
                'similarity': round(score, 4)
            })
        
        results[misra_id] = top_matches
    
    return results


def find_missing_siblings(top_matches: list[dict],
                         fls_sections: dict,
                         similarity_threshold: float = 0.3) -> list[dict]:
    """
    Find "missing siblings" - FLS sections that are siblings of matched sections
    but weren't in the top matches.
    
    Returns list of flagged siblings with their context.
    """
    # Collect all matched FLS IDs above threshold
    matched_ids = {m['fls_id'] for m in top_matches if m['similarity'] >= similarity_threshold}
    
    # For each matched ID, find siblings that weren't matched
    missing = []
    checked_parents = set()
    
    for fls_id in matched_ids:
        section = fls_sections.get(fls_id)
        if not section:
            continue
        
        parent_id = section.get('parent_fls_id')
        if not parent_id or parent_id in checked_parents:
            continue
        
        checked_parents.add(parent_id)
        
        # Get all siblings
        sibling_ids = section.get('sibling_fls_ids', [])
        
        # Find siblings not in matches
        for sib_id in sibling_ids:
            if sib_id not in matched_ids:
                sib_section = fls_sections.get(sib_id)
                if sib_section:
                    missing.append({
                        'fls_id': sib_id,
                        'title': sib_section.get('title', ''),
                        'parent_fls_id': parent_id,
                        'reason': f"Sibling of matched {fls_id}"
                    })
    
    return missing


def find_missing_adjacent(top_matches: list[dict],
                          fls_sections: dict,
                          all_sections: list[dict],
                          similarity_threshold: float = 0.4) -> list[dict]:
    """
    Find adjacent sections (by section number) that might be relevant.
    """
    # This is a simplified version - in practice you'd want to look at 
    # section numbers like 15.1, 15.2, etc.
    # For now, we'll rely on the sibling detection which handles hierarchy
    return []


def main():
    parser = argparse.ArgumentParser(description='Compute MISRA-FLS similarity')
    parser.add_argument('--top-n', type=int, default=20,
                       help='Number of top similar FLS sections')
    args = parser.parse_args()
    
    project_root = get_project_root()
    
    # Load embeddings
    print("Loading embeddings...")
    
    misra_emb_path = project_root / "embeddings" / "misra_c" / "embeddings.pkl"
    fls_emb_path = project_root / "embeddings" / "fls" / "embeddings.pkl"
    
    if not misra_emb_path.exists():
        print(f"Error: MISRA embeddings not found at {misra_emb_path}")
        print("Run generate_embeddings.py first.")
        return 1
    
    if not fls_emb_path.exists():
        print(f"Error: FLS embeddings not found at {fls_emb_path}")
        print("Run generate_embeddings.py first.")
        return 1
    
    misra_data = load_embeddings(misra_emb_path)
    fls_data = load_embeddings(fls_emb_path)
    
    print(f"  MISRA: {misra_data['num_items']} items, dim={misra_data['embedding_dim']}")
    print(f"  FLS: {fls_data['num_items']} items, dim={fls_data['embedding_dim']}")
    
    # Load FLS sections for sibling detection
    print("\nLoading FLS sections metadata...")
    fls_sections = load_fls_sections(project_root)
    print(f"  Loaded {len(fls_sections)} sections")
    
    # Extract arrays
    misra_ids = misra_data['data']['ids']
    misra_embeddings = misra_data['data']['embeddings']
    fls_ids = fls_data['data']['ids']
    fls_embeddings = fls_data['data']['embeddings']
    
    # Compute similarity matrix
    print("\nComputing similarity matrix...")
    similarity_matrix = cosine_similarity(misra_embeddings, fls_embeddings)
    print(f"  Matrix shape: {similarity_matrix.shape}")
    
    # Find top matches
    print(f"\nFinding top {args.top_n} matches for each MISRA guideline...")
    top_matches = find_top_similar(
        similarity_matrix, misra_ids, fls_ids, top_n=args.top_n
    )
    
    # Find missing siblings for each guideline
    print("Finding missing siblings...")
    results = {}
    total_missing = 0
    
    for misra_id, matches in top_matches.items():
        missing = find_missing_siblings(matches, fls_sections)
        total_missing += len(missing)
        
        results[misra_id] = {
            'top_matches': matches,
            'missing_siblings': missing
        }
    
    print(f"  Total missing siblings flagged: {total_missing}")
    
    # Compute statistics
    avg_top_score = np.mean([r['top_matches'][0]['similarity'] for r in results.values()])
    
    # Create output
    output = {
        'generated_date': str(date.today()),
        'model': misra_data['model'],
        'parameters': {
            'top_n': args.top_n
        },
        'statistics': {
            'misra_guidelines': len(misra_ids),
            'fls_sections': len(fls_ids),
            'avg_top_similarity': round(avg_top_score, 4),
            'total_missing_siblings': total_missing
        },
        'results': results
    }
    
    # Save output
    output_path = project_root / "embeddings" / "similarity" / "misra_c_to_fls.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved to: {output_path}")
    
    # Show sample results
    print("\n=== Sample Results ===")
    sample_ids = ['Dir 4.1', 'Rule 11.1', 'Rule 18.1']
    for misra_id in sample_ids:
        if misra_id in results:
            r = results[misra_id]
            print(f"\n{misra_id}:")
            print(f"  Top 5 matches:")
            for m in r['top_matches'][:5]:
                section = fls_sections.get(m['fls_id'], {})
                title = section.get('title', '')[:40]
                print(f"    {m['fls_id']}: {m['similarity']:.3f} - {title}...")
            if r['missing_siblings']:
                print(f"  Missing siblings: {len(r['missing_siblings'])}")
    
    return 0


if __name__ == "__main__":
    exit(main())
