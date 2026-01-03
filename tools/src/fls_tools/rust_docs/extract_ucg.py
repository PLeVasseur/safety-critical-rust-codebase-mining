#!/usr/bin/env python3
"""
extract-ucg: Extract Unsafe Code Guidelines content to JSON.

Extracts content from the UCG mdBook. UCG doesn't have native r[...] markers
like the Reference, so we generate synthetic IDs from headings.

Usage:
    uv run extract-ucg              # Extract all chapters
    uv run extract-ucg --force      # Re-extract even if exists

Output:
    embeddings/ucg/index.json
    embeddings/ucg/chapter_01.json
    embeddings/ucg/chapter_02.json
    ...
"""

import argparse
import json
from datetime import date
from pathlib import Path

from fls_tools.shared import get_project_root, get_cache_dir, get_embeddings_dir
from fls_tools.rust_docs.shared import (
    parse_summary_md,
    parse_heading_based_content,
    Chapter,
)


def get_ucg_src_dir(root: Path) -> Path:
    """Get the UCG source directory."""
    return get_cache_dir(root) / "docs" / "unsafe-code-guidelines" / "reference" / "src"


def get_ucg_output_dir(root: Path) -> Path:
    """Get the UCG embeddings output directory."""
    return get_embeddings_dir(root) / "ucg"


def extract_chapter(
    src_dir: Path,
    chapter: Chapter,
    chapter_num: int,
) -> dict | None:
    """
    Extract a single chapter to JSON format.
    
    Args:
        src_dir: Path to ucg/reference/src/
        chapter: Chapter metadata from SUMMARY.md
        chapter_num: Chapter number (1-indexed)
    
    Returns:
        Chapter data dict ready for JSON serialization
    """
    chapter_path = src_dir / chapter.path
    
    if not chapter_path.exists():
        print(f"  Warning: Chapter file not found: {chapter_path}")
        return None
    
    content = chapter_path.read_text(encoding="utf-8")
    
    # Parse into sections with paragraphs (using synthetic IDs)
    sections = parse_heading_based_content(content, chapter.title, "ucg")
    
    # Convert to JSON-serializable format
    sections_data = []
    all_ids = []
    
    for section in sections:
        para_dict = {}
        for para in section.paragraphs:
            para_dict[para.id] = para.text
            all_ids.append(para.id)
        
        sections_data.append({
            "id": section.id,
            "title": section.title,
            "level": section.level,
            "content": section.content.strip(),
            "parent_id": section.parent_id,
            "paragraphs": para_dict,
        })
        
        if section.id:
            all_ids.append(section.id)
    
    # Also process sub-sections (nested files)
    for subsection in chapter.sections:
        sub_path = src_dir / subsection.path
        if sub_path.exists():
            sub_content = sub_path.read_text(encoding="utf-8")
            sub_sections = parse_heading_based_content(sub_content, subsection.title, "ucg")
            
            for section in sub_sections:
                para_dict = {}
                for para in section.paragraphs:
                    para_dict[para.id] = para.text
                    all_ids.append(para.id)
                
                sections_data.append({
                    "id": section.id,
                    "title": section.title,
                    "level": section.level,
                    "content": section.content.strip(),
                    "parent_id": section.parent_id,
                    "paragraphs": para_dict,
                })
                
                if section.id:
                    all_ids.append(section.id)
    
    return {
        "source": "Unsafe Code Guidelines",
        "source_repo": "https://github.com/rust-lang/unsafe-code-guidelines",
        "extraction_date": str(date.today()),
        "chapter": chapter_num,
        "title": chapter.title,
        "file": chapter.path,
        "sections": sections_data,
        "ids": list(set(all_ids)),  # Deduplicated
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract Unsafe Code Guidelines content to JSON"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-extract even if output exists",
    )
    
    args = parser.parse_args()
    root = get_project_root()
    
    src_dir = get_ucg_src_dir(root)
    output_dir = get_ucg_output_dir(root)
    
    if not src_dir.exists():
        print(f"ERROR: UCG source not found at {src_dir}")
        print("Run: uv run clone-rust-docs --source ucg")
        return 1
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse SUMMARY.md for chapter structure
    summary_path = src_dir / "SUMMARY.md"
    print(f"Parsing {summary_path}...")
    chapters = parse_summary_md(summary_path)
    print(f"  Found {len(chapters)} top-level chapters")
    
    # Extract each chapter
    all_ids = []
    chapter_index = []
    
    for i, chapter in enumerate(chapters):
        chapter_num = i + 1
        print(f"\nExtracting chapter {chapter_num}: {chapter.title}...")
        
        chapter_data = extract_chapter(src_dir, chapter, chapter_num)
        
        if chapter_data is None:
            continue
        
        # Save chapter file
        chapter_file = f"chapter_{chapter_num:02d}.json"
        chapter_path = output_dir / chapter_file
        
        if chapter_path.exists() and not args.force:
            print(f"  Skipping (exists): {chapter_file}")
            # Still load for ID collection
            with open(chapter_path, encoding="utf-8") as f:
                chapter_data = json.load(f)
        else:
            with open(chapter_path, "w", encoding="utf-8") as f:
                json.dump(chapter_data, f, indent=2)
                f.write("\n")
            print(f"  Saved: {chapter_file}")
        
        # Collect IDs
        for section in chapter_data.get("sections", []):
            section_id = section.get("id")
            if section_id:
                all_ids.append(section_id)
            
            for para_id in section.get("paragraphs", {}).keys():
                all_ids.append(para_id)
        
        # Track for index
        section_count = len(chapter_data.get("sections", []))
        para_count = sum(
            len(s.get("paragraphs", {})) 
            for s in chapter_data.get("sections", [])
        )
        
        chapter_index.append({
            "chapter": chapter_num,
            "title": chapter_data["title"],
            "file": chapter_file,
            "sections": section_count,
            "paragraphs": para_count,
        })
    
    # Save index
    index_data = {
        "source": "Unsafe Code Guidelines",
        "source_repo": "https://github.com/rust-lang/unsafe-code-guidelines",
        "extraction_date": str(date.today()),
        "total_chapters": len(chapter_index),
        "total_sections": sum(c["sections"] for c in chapter_index),
        "total_paragraphs": sum(c["paragraphs"] for c in chapter_index),
        "total_ids": len(set(all_ids)),
        "chapters": chapter_index,
    }
    
    index_path = output_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)
        f.write("\n")
    print(f"\nSaved index: {index_path}")
    
    # Summary
    print(f"\n{'='*60}")
    print("EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Chapters:   {index_data['total_chapters']}")
    print(f"Sections:   {index_data['total_sections']}")
    print(f"Paragraphs: {index_data['total_paragraphs']}")
    print(f"Unique IDs: {index_data['total_ids']}")
    
    return 0


if __name__ == "__main__":
    exit(main())
