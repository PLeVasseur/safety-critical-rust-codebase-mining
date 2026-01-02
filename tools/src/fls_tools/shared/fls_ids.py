"""
FLS ID validation utilities.

This module provides functions for:
- Generating a flat list of all valid FLS IDs from canonical sources
- Loading the pre-generated valid FLS IDs
- Validating FLS IDs against the valid set

Valid FLS IDs come from three sources:
1. Section-level IDs from fls_section_mapping.json
2. Synthetic IDs from synthetic_fls_ids.json
3. Paragraph-level IDs from embeddings/fls/chapter_*.json

The flat list is stored in tools/data/valid_fls_ids.json and is regenerated
automatically when extract-fls-content is run.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import (
    get_project_root,
    get_data_dir,
    get_fls_dir,
    get_fls_section_mapping_path,
    get_synthetic_fls_ids_path,
)


def get_valid_fls_ids_path(root: Path | None = None) -> Path:
    """Get the path to the valid FLS IDs file."""
    if root is None:
        root = get_project_root()
    return get_data_dir(root) / "valid_fls_ids.json"


def extract_ids_from_section_mapping(root: Path) -> set[str]:
    """
    Extract all FLS IDs from fls_section_mapping.json.
    
    This includes section-level IDs and fabricated section IDs.
    """
    mapping_path = get_fls_section_mapping_path(root)
    if not mapping_path.exists():
        return set()
    
    with open(mapping_path) as f:
        mapping = json.load(f)
    
    ids = set()
    
    def extract_recursive(obj: dict | list) -> None:
        if isinstance(obj, dict):
            if "fls_id" in obj and obj["fls_id"]:
                ids.add(obj["fls_id"])
            for value in obj.values():
                extract_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_recursive(item)
    
    extract_recursive(mapping)
    return ids


def extract_ids_from_synthetic(root: Path) -> set[str]:
    """
    Extract all FLS IDs from synthetic_fls_ids.json.
    """
    synthetic_path = get_synthetic_fls_ids_path(root)
    if not synthetic_path.exists():
        return set()
    
    with open(synthetic_path) as f:
        synthetic = json.load(f)
    
    ids = set()
    for entry in synthetic.get("ids", []):
        if "fls_id" in entry:
            ids.add(entry["fls_id"])
    
    return ids


def extract_ids_from_embeddings(root: Path) -> set[str]:
    """
    Extract all FLS IDs from embeddings/fls/chapter_*.json.
    
    This includes:
    - Section-level fls_id fields
    - Paragraph-level IDs in rubrics
    """
    fls_dir = get_fls_dir(root)
    if not fls_dir.exists():
        return set()
    
    ids = set()
    
    for chapter_file in sorted(fls_dir.glob("chapter_*.json")):
        with open(chapter_file) as f:
            chapter = json.load(f)
        
        # Chapter-level FLS ID
        if chapter.get("fls_id"):
            ids.add(chapter["fls_id"])
        
        # Section-level FLS IDs and paragraph IDs
        for section in chapter.get("sections", []):
            if section.get("fls_id"):
                ids.add(section["fls_id"])
            
            # Paragraph IDs within rubrics
            for rubric_data in section.get("rubrics", {}).values():
                for para_id in rubric_data.get("paragraphs", {}).keys():
                    # Skip synthetic syntax IDs like "syntax_1"
                    if para_id.startswith("fls_"):
                        ids.add(para_id)
    
    return ids


def generate_valid_fls_ids(root: Path | None = None) -> dict:
    """
    Generate the valid_fls_ids.json file from all canonical sources.
    
    Returns the generated data structure.
    """
    if root is None:
        root = get_project_root()
    
    # Collect IDs from all sources
    section_ids = extract_ids_from_section_mapping(root)
    synthetic_ids = extract_ids_from_synthetic(root)
    embedding_ids = extract_ids_from_embeddings(root)
    
    # Combine all IDs
    all_ids = section_ids | synthetic_ids | embedding_ids
    
    # Build output structure
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [
            "fls_section_mapping.json",
            "synthetic_fls_ids.json",
            "embeddings/fls/chapter_*.json",
        ],
        "counts": {
            "section_mapping": len(section_ids),
            "synthetic": len(synthetic_ids),
            "embeddings": len(embedding_ids),
            "total_unique": len(all_ids),
        },
        "ids": sorted(all_ids),
    }
    
    # Write to file
    output_path = get_valid_fls_ids_path(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    
    return data


def load_valid_fls_ids(root: Path | None = None) -> set[str]:
    """
    Load the set of valid FLS IDs from the pre-generated file.
    
    Raises FileNotFoundError if the file doesn't exist.
    """
    if root is None:
        root = get_project_root()
    
    ids_path = get_valid_fls_ids_path(root)
    
    if not ids_path.exists():
        raise FileNotFoundError(
            f"Valid FLS IDs file not found: {ids_path}\n"
            f"Run 'uv run generate-valid-fls-ids' to generate it."
        )
    
    with open(ids_path) as f:
        data = json.load(f)
    
    return set(data.get("ids", []))


def validate_fls_id(fls_id: str, valid_ids: set[str] | None = None) -> tuple[bool, str]:
    """
    Validate an FLS ID against the set of valid IDs.
    
    Args:
        fls_id: The FLS ID to validate (e.g., "fls_abc123")
        valid_ids: Optional pre-loaded set of valid IDs. If None, loads from file.
    
    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    # Basic format check
    if not fls_id.startswith("fls_"):
        return False, f"Invalid FLS ID format: '{fls_id}'. Must start with 'fls_'"
    
    # Load valid IDs if not provided
    if valid_ids is None:
        try:
            valid_ids = load_valid_fls_ids()
        except FileNotFoundError as e:
            return False, str(e)
    
    # Check if ID is in valid set
    if fls_id not in valid_ids:
        return False, (
            f"Unknown FLS ID: '{fls_id}'\n"
            f"\n"
            f"This FLS ID does not exist in any canonical source. Please verify:\n"
            f"  1. Check the FLS ID from your search results\n"
            f"  2. Use search-fls or search-fls-deep to find the correct ID\n"
            f"  3. Ensure the ID matches exactly (case-sensitive)"
        )
    
    return True, ""
