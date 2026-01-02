#!/usr/bin/env python3
"""
Extract FLS section content from RST files for embedding generation.

This script parses the Ferrocene Language Specification RST files and extracts:
- Section-level FLS IDs (.. _fls_xxx: anchors)
- Paragraph-level FLS IDs (:dp:`fls_xxx` markers)
- Section hierarchy (parent -> children relationships)
- Rubric-categorized paragraphs (legality rules, UB, dynamic semantics, etc.)
- Full prose content for each section

The extracted content is saved to embeddings/fls/ as:
- index.json: Chapter listing and aggregate statistics
- chapter_NN.json: Per-chapter section data with rubric-categorized paragraphs

Category Codes:
    0  = section (section-level entry, container)
   -1  = general (intro/definition text before first rubric)
   -2  = legality_rules (compiler-enforced rules)
   -3  = dynamic_semantics (runtime/dynamic semantics)
   -4  = undefined_behavior (UB definitions)
   -5  = implementation_requirements
   -6  = implementation_permissions
   -7  = examples (code examples)
   -8  = syntax (syntax blocks/grammar)

Usage:
    uv run python tools/embeddings/extract_fls_content.py

Output:
    embeddings/fls/index.json
    embeddings/fls/chapter_01.json
    embeddings/fls/chapter_02.json
    ...
"""

import json
import re
from datetime import date
from pathlib import Path

# Category codes for rubric types
CATEGORY_CODES = {
    "section": 0,
    "general": -1,
    "legality_rules": -2,
    "dynamic_semantics": -3,
    "undefined_behavior": -4,
    "implementation_requirements": -5,
    "implementation_permissions": -6,
    "examples": -7,
    "syntax": -8,
}

# Reverse mapping for JSON output
CATEGORY_NAMES = {v: k for k, v in CATEGORY_CODES.items()}

# RST rubric text to category code mapping
RUBRIC_TO_CATEGORY = {
    "Legality Rules": -2,
    "Dynamic Semantics": -3,
    "Runtime Semantics": -3,  # Alias for dynamic semantics
    "Undefined Behavior": -4,
    "Implementation Requirements": -5,
    "Implementation Permissions": -6,
    "Examples": -7,
    "Syntax": -8,
}

# Chapter ordering from FLS index.rst (1-indexed)
CHAPTER_ORDER = [
    "general",                          # 1
    "lexical-elements",                 # 2
    "items",                            # 3
    "types-and-traits",                 # 4
    "patterns",                         # 5
    "expressions",                      # 6
    "values",                           # 7
    "statements",                       # 8
    "functions",                        # 9
    "associated-items",                 # 10
    "implementations",                  # 11
    "generics",                         # 12
    "attributes",                       # 13
    "entities-and-resolution",          # 14
    "ownership-and-deconstruction",     # 15
    "exceptions-and-errors",            # 16
    "concurrency",                      # 17
    "program-structure-and-compilation", # 18
    "unsafety",                         # 19
    "macros",                           # 20
    "ffi",                              # 21
    "inline-assembly",                  # 22
]

# Chapter titles
CHAPTER_TITLES = {
    "general": "General",
    "lexical-elements": "Lexical Elements",
    "items": "Items",
    "types-and-traits": "Types and Traits",
    "patterns": "Patterns",
    "expressions": "Expressions",
    "values": "Values",
    "statements": "Statements",
    "functions": "Functions",
    "associated-items": "Associated Items",
    "implementations": "Implementations",
    "generics": "Generics",
    "attributes": "Attributes",
    "entities-and-resolution": "Entities and Resolution",
    "ownership-and-deconstruction": "Ownership and Destruction",
    "exceptions-and-errors": "Exceptions and Errors",
    "concurrency": "Concurrency",
    "program-structure-and-compilation": "Program Structure and Compilation",
    "unsafety": "Unsafety",
    "macros": "Macros",
    "ffi": "FFI",
    "inline-assembly": "Inline Assembly",
}


from fls_tools.shared import (
    get_project_root,
    get_fls_dir,
    get_fls_repo_dir,
    generate_valid_fls_ids,
)


# get_project_root is imported from fls_tools.shared


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


def extract_rubrics(content: str) -> list[tuple[int, int, str]]:
    """
    Extract all rubric positions with their category codes.
    Returns list of (position, category_code, rubric_name).
    """
    pattern = r'\.\.\s+rubric::\s*([^\n]+)'
    rubrics = []
    for match in re.finditer(pattern, content):
        rubric_name = match.group(1).strip()
        category_code = RUBRIC_TO_CATEGORY.get(rubric_name)
        if category_code is not None:
            rubrics.append((match.start(), category_code, rubric_name))
    return rubrics


def extract_syntax_blocks(content: str, start: int, end: int) -> list[tuple[str, str]]:
    """
    Extract syntax blocks within a section range.
    Returns list of (paragraph_id or generated_id, syntax_text).
    
    Syntax blocks are truncated to 500 chars.
    """
    section_content = content[start:end]
    
    # Find .. syntax:: blocks
    pattern = r'\.\.\s+syntax::\s*\n([\s\S]*?)(?=\n\n[^\s]|\n\.\.|$)'
    blocks = []
    
    for match in re.finditer(pattern, section_content):
        syntax_text = match.group(1).strip()
        # Clean up indentation
        lines = syntax_text.split('\n')
        # Remove common leading whitespace
        if lines:
            min_indent = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
            syntax_text = '\n'.join(line[min_indent:] if len(line) > min_indent else line for line in lines)
        
        # Truncate if too long
        if len(syntax_text) > 500:
            syntax_text = syntax_text[:500] + "..."
        
        blocks.append(syntax_text)
    
    return blocks


def clean_paragraph_text(text: str) -> str:
    """
    Clean RST markup from paragraph text for readability.
    Strips :t:, :c:, :std:, :dt:, :dp:, :p:, :s: markers and normalizes whitespace.
    """
    # Remove :dp: markers (paragraph IDs)
    text = re.sub(r':dp:`[^`]+`\s*', '', text)
    # Remove cross-references (:p:)
    text = re.sub(r':p:`[^`]+`', '', text)
    # Remove term/concept markers, keeping the text
    text = re.sub(r':t:`([^`]+)`', r'\1', text)
    text = re.sub(r':c:`([^`]+)`', r'\1', text)
    text = re.sub(r':std:`([^`]+)`', r'\1', text)
    text = re.sub(r':dt:`([^`]+)`', r'\1', text)
    text = re.sub(r':s:`([^`]+)`', r'\1', text)
    # Remove code backticks
    text = re.sub(r'``([^`]+)``', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove bullet point markers
    text = re.sub(r'^\s*\*\s+', '', text, flags=re.MULTILINE)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_paragraph_text(content: str, para_start: int, para_end: int) -> str:
    """
    Extract and clean paragraph text between positions.
    """
    para_text = content[para_start:para_end]
    return clean_paragraph_text(para_text)


def extract_paragraphs_by_rubric(
    content: str,
    start: int,
    end: int,
    rubrics: list[tuple[int, int, str]],
    paragraphs: list[tuple[int, str]]
) -> dict[str, dict]:
    """
    Extract paragraphs in range [start, end) grouped by their rubric category.
    
    Returns dict mapping category_code (as string) -> {paragraphs: {pid: text}}
    """
    result = {}
    
    # Filter rubrics and paragraphs to this section's range
    section_rubrics = [(pos, cat, name) for pos, cat, name in rubrics if start <= pos < end]
    section_paragraphs = [(pos, pid) for pos, pid in paragraphs if start < pos < end]
    
    # Sort rubrics by position
    section_rubrics.sort(key=lambda x: x[0])
    
    # Track syntax block counter for this section
    syntax_counter = 0
    
    for ppos, pid in section_paragraphs:
        # Find the most recent rubric before this paragraph
        current_category = -1  # Default to general if before first rubric
        for rpos, cat, name in section_rubrics:
            if rpos < ppos:
                current_category = cat
            else:
                break
        
        # Find paragraph text boundaries
        # From :dp: marker to next :dp:, rubric, section anchor, or section end
        dp_pattern = rf':dp:`{pid}`'
        match = re.search(dp_pattern, content[start:end])
        if not match:
            continue
        
        para_start = start + match.end()
        remaining = content[para_start:end]
        
        # Find next boundary
        next_markers = []
        
        # Next paragraph marker
        dp_match = re.search(r':dp:`', remaining)
        if dp_match:
            next_markers.append(dp_match.start())
        
        # Next rubric
        rubric_match = re.search(r'\.\.\s+rubric::', remaining)
        if rubric_match:
            next_markers.append(rubric_match.start())
        
        # Next section anchor
        anchor_match = re.search(r'\.\.\s+_fls_', remaining)
        if anchor_match:
            next_markers.append(anchor_match.start())
        
        # Next syntax block
        syntax_match = re.search(r'\.\.\s+syntax::', remaining)
        if syntax_match:
            next_markers.append(syntax_match.start())
        
        if next_markers:
            para_end = para_start + min(next_markers)
        else:
            para_end = end
        
        para_text = extract_paragraph_text(content, para_start, para_end)
        
        if para_text and len(para_text) > 5:  # Skip very short/empty paragraphs
            cat_key = str(current_category)
            if cat_key not in result:
                result[cat_key] = {"paragraphs": {}}
            result[cat_key]["paragraphs"][pid] = para_text
    
    # Extract syntax blocks
    syntax_blocks = extract_syntax_blocks(content, start, end)
    if syntax_blocks:
        cat_key = str(CATEGORY_CODES["syntax"])
        if cat_key not in result:
            result[cat_key] = {"paragraphs": {}}
        for i, syntax_text in enumerate(syntax_blocks):
            # Generate a synthetic ID for syntax blocks
            syntax_id = f"syntax_{i+1}"
            result[cat_key]["paragraphs"][syntax_id] = syntax_text
    
    return result


def extract_section_content(content: str, start: int, end: int) -> str:
    """Extract and clean section content between positions for embeddings."""
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
    section_text = re.sub(r':p:`([^`]+)`', r'\1', section_text)
    section_text = re.sub(r':s:`([^`]+)`', r'\1', section_text)
    section_text = re.sub(r'``([^`]+)``', r'\1', section_text)
    
    # Remove underlines
    section_text = re.sub(r'\n[=\-~^"]{3,}\n', '\n', section_text)
    
    # Clean up excessive whitespace
    section_text = re.sub(r'\n{3,}', '\n\n', section_text)
    section_text = re.sub(r' +', ' ', section_text)
    
    return section_text.strip()


def parse_rst_file(file_path: Path) -> list[dict]:
    """
    Parse an RST file and extract all FLS sections with hierarchy and rubric content.
    Returns list of section dictionaries.
    """
    content = file_path.read_text(encoding='utf-8')
    
    # Extract all anchors, paragraphs, titles, and rubrics
    anchors = extract_fls_anchors(content)
    paragraphs = extract_paragraph_ids(content)
    titles = extract_section_titles(content)
    rubrics = extract_rubrics(content)
    
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
        
        # Extract content for embeddings
        section_content = extract_section_content(content, anchor_pos, end_pos)
        
        # Extract paragraphs grouped by rubric
        rubric_content = extract_paragraphs_by_rubric(
            content, anchor_pos, end_pos, rubrics, paragraphs
        )
        
        sections.append({
            "fls_id": fls_id,
            "title": title,
            "category": CATEGORY_CODES["section"],
            "level": level,
            "file": file_path.stem,
            "content": section_content,
            "rubrics": rubric_content,
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


def compute_statistics(sections: list[dict]) -> dict:
    """
    Compute statistics for a list of sections.
    """
    total_paragraphs = 0
    by_category = {}
    
    for s in sections:
        for cat_key, rubric_data in s.get('rubrics', {}).items():
            para_count = len(rubric_data.get('paragraphs', {}))
            total_paragraphs += para_count
            cat_int = int(cat_key)
            by_category[cat_int] = by_category.get(cat_int, 0) + para_count
    
    # Convert keys to strings for JSON
    by_category_str = {str(k): v for k, v in sorted(by_category.items())}
    
    return {
        "total_sections": len(sections),
        "total_paragraphs": total_paragraphs,
        "paragraphs_by_category": by_category_str
    }


def main():
    """Main extraction function."""
    project_root = get_project_root()
    fls_src = get_fls_repo_dir(project_root) / "src"
    output_dir = get_fls_dir(project_root)
    
    if not fls_src.exists():
        print(f"Error: FLS source not found at {fls_src}")
        return 1
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process each chapter
    chapters_data = []
    all_sections = []
    aggregate_stats = {
        "total_sections": 0,
        "total_paragraphs": 0,
        "paragraphs_by_category": {}
    }
    
    print(f"Processing {len(CHAPTER_ORDER)} chapters...")
    
    for chapter_num, file_stem in enumerate(CHAPTER_ORDER, start=1):
        rst_file = fls_src / f"{file_stem}.rst"
        
        if not rst_file.exists():
            print(f"  Warning: Chapter {chapter_num} file not found: {rst_file.name}")
            continue
        
        print(f"  Chapter {chapter_num:02d}: {file_stem}")
        
        # Parse the RST file
        sections = parse_rst_file(rst_file)
        
        # Build hierarchy within this file
        sections = build_hierarchy(sections)
        sections = add_sibling_info(sections)
        
        # Remove position field (was only for ordering)
        for s in sections:
            del s['position']
        
        # Find chapter-level FLS ID (first section at level 1)
        chapter_fls_id = None
        for s in sections:
            if s['level'] == 1:
                chapter_fls_id = s['fls_id']
                break
        
        # Compute statistics
        stats = compute_statistics(sections)
        
        # Update aggregate stats
        aggregate_stats["total_sections"] += stats["total_sections"]
        aggregate_stats["total_paragraphs"] += stats["total_paragraphs"]
        for cat, count in stats["paragraphs_by_category"].items():
            aggregate_stats["paragraphs_by_category"][cat] = \
                aggregate_stats["paragraphs_by_category"].get(cat, 0) + count
        
        # Create chapter output
        chapter_output = {
            "chapter": chapter_num,
            "title": CHAPTER_TITLES.get(file_stem, file_stem),
            "fls_id": chapter_fls_id,
            "file": file_stem,
            "extraction_date": str(date.today()),
            "category_codes": {str(v): k for k, v in CATEGORY_CODES.items()},
            "statistics": stats,
            "sections": sections
        }
        
        # Save chapter file
        chapter_file = output_dir / f"chapter_{chapter_num:02d}.json"
        with open(chapter_file, 'w', encoding='utf-8') as f:
            json.dump(chapter_output, f, indent=2, ensure_ascii=False)
        
        print(f"    Sections: {stats['total_sections']}, Paragraphs: {stats['total_paragraphs']}")
        
        # Track for index
        chapters_data.append({
            "chapter": chapter_num,
            "title": CHAPTER_TITLES.get(file_stem, file_stem),
            "fls_id": chapter_fls_id,
            "file": f"chapter_{chapter_num:02d}.json",
            "sections": stats["total_sections"],
            "paragraphs": stats["total_paragraphs"]
        })
        
        all_sections.extend(sections)
    
    # Sort aggregate stats by category
    aggregate_stats["paragraphs_by_category"] = dict(
        sorted(aggregate_stats["paragraphs_by_category"].items(), key=lambda x: int(x[0]))
    )
    
    # Create index file
    index_output = {
        "source": "FLS RST files",
        "extraction_date": str(date.today()),
        "category_codes": {str(v): k for k, v in CATEGORY_CODES.items()},
        "chapters": chapters_data,
        "aggregate_statistics": aggregate_stats
    }
    
    index_file = output_dir / "index.json"
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index_output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved index to: {index_file}")
    
    # Print summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print(f"  Chapters processed: {len(chapters_data)}")
    print(f"  Total sections: {aggregate_stats['total_sections']}")
    print(f"  Total paragraphs: {aggregate_stats['total_paragraphs']}")
    print(f"\n  Paragraphs by category:")
    for cat, count in aggregate_stats["paragraphs_by_category"].items():
        cat_name = CATEGORY_NAMES.get(int(cat), "unknown")
        print(f"    {cat:>3} ({cat_name:25}): {count:5}")
    
    # Show sample section
    if all_sections:
        sample = all_sections[10] if len(all_sections) > 10 else all_sections[0]
        print(f"\nSample section:")
        print(f"  FLS ID: {sample['fls_id']}")
        print(f"  Title: {sample['title']}")
        print(f"  Category: {sample['category']}")
        print(f"  Level: {sample['level']}")
        print(f"  Content length: {len(sample['content'])} chars")
        print(f"  Rubrics: {list(sample['rubrics'].keys())}")
        for cat_key, rubric_data in sample['rubrics'].items():
            para_count = len(rubric_data.get('paragraphs', {}))
            cat_name = CATEGORY_NAMES.get(int(cat_key), "unknown")
            print(f"    {cat_key} ({cat_name}): {para_count} paragraphs")
    
    # Generate valid FLS IDs file for downstream validation
    print(f"\n{'='*60}")
    print("Generating valid FLS IDs file...")
    print(f"{'='*60}")
    valid_ids_path, id_count = generate_valid_fls_ids(project_root)
    print(f"  Generated: {valid_ids_path}")
    print(f"  Total valid FLS IDs: {id_count}")
    
    return 0


if __name__ == "__main__":
    exit(main())
