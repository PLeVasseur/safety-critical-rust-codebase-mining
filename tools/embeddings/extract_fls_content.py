#!/usr/bin/env python3
"""
Extract FLS section content from RST files for embedding generation.

This script parses the Ferrocene Language Specification RST files and extracts:
- Section-level FLS IDs (.. _fls_xxx: anchors)
- Paragraph-level FLS IDs (:dp:`fls_xxx` markers)
- Section hierarchy (parent → children relationships)
- Full prose content for each section

The extracted content is saved to embeddings/fls/sections.json for:
1. Generating vector embeddings
2. Hierarchical "missing sibling" detection during verification

Usage:
    uv run python tools/embeddings/extract_fls_content.py

Output:
    embeddings/fls/sections.json
"""

import json
import re
from datetime import date
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def get_section_level(underline: str) -> int:
    """
    Determine section level based on RST underline character.
    = (with overline) -> 0 (document title)
    = -> 1 (chapter)
    - -> 2 (section)
    ~ -> 3 (subsection)
    ^ -> 4 (sub-subsection)
    """
    char = underline[0] if underline else ''
    levels = {'=': 1, '-': 2, '~': 3, '^': 4, '"': 5}
    return levels.get(char, 1)


def extract_fls_anchors(content: str) -> list[tuple[int, str]]:
    """
    Extract all FLS section anchors (.. _fls_xxx:) with their positions.
    Returns list of (position, fls_id).
    """
    pattern = r'\.\.\s+_fls_([a-zA-Z0-9]+):'
    anchors = []
    for match in re.finditer(pattern, content):
        fls_id = f"fls_{match.group(1)}"
        anchors.append((match.start(), fls_id))
    return anchors


def extract_paragraph_ids(content: str) -> list[tuple[int, str]]:
    """
    Extract all paragraph-level FLS IDs (:dp:`fls_xxx`) with positions.
    Returns list of (position, fls_id).
    """
    pattern = r':dp:`(fls_[a-zA-Z0-9]+)`'
    paragraphs = []
    for match in re.finditer(pattern, content):
        paragraphs.append((match.start(), match.group(1)))
    return paragraphs


def extract_section_titles(content: str) -> list[tuple[int, str, int]]:
    """
    Extract section titles with their positions and levels.
    Returns list of (position, title, level).
    """
    # RST section pattern: title line followed by underline of same or greater length
    # The underline character determines the level
    lines = content.split('\n')
    sections = []
    
    i = 0
    while i < len(lines) - 1:
        line = lines[i].strip()
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        
        # Check if next line is an underline (all same character, length >= title)
        if line and next_line and len(next_line) >= len(line):
            underline_char = next_line[0]
            if underline_char in '=-~^"' and all(c == underline_char for c in next_line.strip()):
                # Find position in original content
                pos = content.find(line + '\n' + next_line)
                if pos >= 0:
                    level = get_section_level(underline_char)
                    sections.append((pos, line, level))
        i += 1
    
    return sections


def extract_section_content(content: str, start: int, end: int) -> str:
    """Extract and clean section content between positions."""
    section_text = content[start:end]
    
    # Remove RST directives we don't need for embeddings
    section_text = re.sub(r'\.\.\s+rubric::[^\n]+\n', '', section_text)
    section_text = re.sub(r'\.\.\s+syntax::\n[\s\S]*?(?=\n\n|\Z)', '', section_text)
    section_text = re.sub(r'\.\.\s+informational-section::\n', '', section_text)
    section_text = re.sub(r'\.\.\s+list-table::\n[\s\S]*?(?=\n\n[^\s]|\Z)', '', section_text)
    section_text = re.sub(r'\.\.\s+code-block::[^\n]*\n[\s\S]*?(?=\n\n[^\s]|\Z)', '', section_text)
    
    # Remove anchor definitions
    section_text = re.sub(r'\.\.\s+_fls_[a-zA-Z0-9]+:\n*', '', section_text)
    
    # Clean up paragraph ID markers but keep the text
    section_text = re.sub(r':dp:`fls_[a-zA-Z0-9]+`\s*', '', section_text)
    
    # Remove RST formatting markers
    section_text = re.sub(r':t:`([^`]+)`', r'\1', section_text)
    section_text = re.sub(r':c:`([^`]+)`', r'\1', section_text)
    section_text = re.sub(r':std:`([^`]+)`', r'\1', section_text)
    section_text = re.sub(r':dt:`([^`]+)`', r'\1', section_text)
    section_text = re.sub(r'``([^`]+)``', r'\1', section_text)
    
    # Remove underlines
    section_text = re.sub(r'\n[=\-~^"]{3,}\n', '\n', section_text)
    
    # Clean up excessive whitespace
    section_text = re.sub(r'\n{3,}', '\n\n', section_text)
    section_text = re.sub(r' +', ' ', section_text)
    
    return section_text.strip()


def parse_rst_file(file_path: Path) -> list[dict]:
    """
    Parse an RST file and extract all FLS sections with hierarchy.
    Returns list of section dictionaries.
    """
    content = file_path.read_text(encoding='utf-8')
    
    # Extract all anchors, paragraphs, and titles
    anchors = extract_fls_anchors(content)
    paragraphs = extract_paragraph_ids(content)
    titles = extract_section_titles(content)
    
    sections = []
    
    # Process each anchor as a section
    for i, (anchor_pos, fls_id) in enumerate(anchors):
        # Find the associated title (next title after this anchor)
        title = ""
        level = 1
        title_pos = anchor_pos
        
        for tpos, ttitle, tlevel in titles:
            if tpos > anchor_pos:
                title = ttitle
                level = tlevel
                title_pos = tpos
                break
        
        # Find the end of this section (next anchor or end of file)
        if i + 1 < len(anchors):
            end_pos = anchors[i + 1][0]
        else:
            end_pos = len(content)
        
        # Extract content
        section_content = extract_section_content(content, anchor_pos, end_pos)
        
        # Find paragraph IDs within this section
        child_paragraph_ids = []
        for ppos, pid in paragraphs:
            if anchor_pos < ppos < end_pos:
                child_paragraph_ids.append(pid)
        
        sections.append({
            "fls_id": fls_id,
            "title": title,
            "level": level,
            "file": file_path.stem,
            "content": section_content,
            "paragraph_ids": child_paragraph_ids,
            "position": anchor_pos
        })
    
    return sections


def build_hierarchy(sections: list[dict]) -> list[dict]:
    """
    Build parent-child relationships between sections based on level and position.
    """
    # Sort by file and position
    sections_sorted = sorted(sections, key=lambda s: (s['file'], s['position']))
    
    # Track section stack for hierarchy
    stack = []  # Stack of (level, fls_id)
    
    for section in sections_sorted:
        level = section['level']
        fls_id = section['fls_id']
        
        # Pop stack until we find a parent (lower level)
        while stack and stack[-1][0] >= level:
            stack.pop()
        
        # Set parent if stack is not empty
        if stack:
            section['parent_fls_id'] = stack[-1][1]
        else:
            section['parent_fls_id'] = None
        
        # Push current section onto stack
        stack.append((level, fls_id))
    
    return sections_sorted


def add_sibling_info(sections: list[dict]) -> list[dict]:
    """
    Add sibling FLS IDs for each section (same parent, same level).
    """
    # Group by parent
    by_parent = {}
    for s in sections:
        parent = s.get('parent_fls_id')
        if parent not in by_parent:
            by_parent[parent] = []
        by_parent[parent].append(s['fls_id'])
    
    # Add siblings to each section
    for s in sections:
        parent = s.get('parent_fls_id')
        siblings = by_parent.get(parent, [])
        s['sibling_fls_ids'] = [sib for sib in siblings if sib != s['fls_id']]
    
    return sections


def main():
    """Main extraction function."""
    project_root = get_project_root()
    fls_src = project_root / "cache" / "repos" / "fls" / "src"
    output_path = project_root / "embeddings" / "fls" / "sections.json"
    
    if not fls_src.exists():
        print(f"Error: FLS source not found at {fls_src}")
        return 1
    
    # Find all RST files (excluding index, changelog, glossary)
    rst_files = [
        f for f in fls_src.glob("*.rst")
        if f.stem not in ['index', 'changelog', 'glossary', 'licenses', 'conf', 'background']
    ]
    
    print(f"Found {len(rst_files)} RST files")
    
    # Extract sections from each file
    all_sections = []
    for rst_file in sorted(rst_files):
        print(f"  Processing: {rst_file.name}")
        sections = parse_rst_file(rst_file)
        all_sections.extend(sections)
        print(f"    Found {len(sections)} sections")
    
    print(f"\nTotal sections: {len(all_sections)}")
    
    # Build hierarchy
    print("Building hierarchy...")
    all_sections = build_hierarchy(all_sections)
    
    # Add sibling info
    print("Adding sibling information...")
    all_sections = add_sibling_info(all_sections)
    
    # Count paragraph IDs
    total_paragraphs = sum(len(s['paragraph_ids']) for s in all_sections)
    
    # Create output structure
    output = {
        "source": "FLS RST files",
        "extraction_date": str(date.today()),
        "statistics": {
            "total_sections": len(all_sections),
            "total_paragraph_ids": total_paragraphs,
            "files_processed": len(rst_files)
        },
        "sections": all_sections
    }
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to: {output_path}")
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Total sections: {len(all_sections)}")
    print(f"  Total paragraph IDs: {total_paragraphs}")
    
    # Show sample
    if all_sections:
        sample = all_sections[0]
        print(f"\nSample section:")
        print(f"  FLS ID: {sample['fls_id']}")
        print(f"  Title: {sample['title']}")
        print(f"  Level: {sample['level']}")
        print(f"  Content length: {len(sample['content'])} chars")
        print(f"  Paragraph IDs: {len(sample['paragraph_ids'])}")
    
    return 0


if __name__ == "__main__":
    exit(main())
