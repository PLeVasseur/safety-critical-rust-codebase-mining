"""
Shared utilities for parsing mdBook-based Rust documentation.

This module provides common functionality for extracting content from:
- Rust Reference (with r[...] markers)
- Unsafe Code Guidelines (with markdown anchors)
- Rustonomicon (headings only)

All three use mdBook format with SUMMARY.md defining structure.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class Chapter:
    """Represents a chapter in an mdBook."""
    number: int
    title: str
    path: str  # Relative path from src/
    level: int = 1  # Nesting level (1 = top-level)
    sections: list["Chapter"] = field(default_factory=list)


@dataclass
class Paragraph:
    """Represents a paragraph with optional ID."""
    id: str  # Native ID (r[...]) or synthetic
    text: str
    heading_context: str = ""  # Parent heading for context


@dataclass 
class Section:
    """Represents a section within a chapter."""
    id: str
    title: str
    level: int  # Heading level (1-6)
    content: str  # Full content (for section-level embedding)
    paragraphs: list[Paragraph] = field(default_factory=list)
    parent_id: str | None = None


# =============================================================================
# SUMMARY.md Parsing
# =============================================================================

def parse_summary_md(summary_path: Path) -> list[Chapter]:
    """
    Parse SUMMARY.md to extract chapter hierarchy.
    
    mdBook SUMMARY.md format varies:
        # Title
        
        [Introduction](intro.md)
        
        - [Chapter 1](chapter1.md)           # dash style
            - [Section 1.1](chapter1/s1.md)  # 4-space indent
        
        * [Chapter 2](chapter2.md)           # asterisk style
          * [Section 2.1](chapter2/s1.md)    # 2-space indent
    
    Returns list of top-level chapters with nested sections.
    """
    if not summary_path.exists():
        raise FileNotFoundError(f"SUMMARY.md not found: {summary_path}")
    
    content = summary_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    chapters = []
    chapter_num = 0
    
    # Pattern: optional leading whitespace, optional bullet (- or *), [Title](path.md)
    link_pattern = re.compile(r'^(\s*)(?:[-*]\s*)?\[([^\]]+)\]\(([^)]+)\)')
    
    for line in lines:
        match = link_pattern.match(line)
        if not match:
            continue
        
        indent, title, path = match.groups()
        
        # Skip non-markdown files
        if not path.endswith('.md'):
            continue
        
        # Calculate nesting level from indentation
        # Different mdBooks use different indent sizes (2 or 4 spaces)
        indent_len = len(indent)
        if indent_len == 0:
            level = 1
        elif indent_len <= 2:
            level = 2
        elif indent_len <= 4:
            level = 2 if indent_len == 2 else (3 if indent_len == 3 else 2)
        else:
            # For deeper indentation, estimate based on indent
            level = (indent_len // 2) + 1
        
        if level == 1:
            chapter_num += 1
            chapters.append(Chapter(
                number=chapter_num,
                title=title.strip(),
                path=path,
                level=level,
            ))
        elif chapters:
            # Add as section to most recent chapter
            # (simplified - doesn't handle deep nesting)
            chapters[-1].sections.append(Chapter(
                number=len(chapters[-1].sections) + 1,
                title=title.strip(),
                path=path,
                level=level,
            ))
    
    return chapters


# =============================================================================
# Reference r[...] ID Extraction
# =============================================================================

# Pattern for r[id.here] markers
REFERENCE_ID_PATTERN = re.compile(r'^r\[([a-z][a-z0-9._-]*)\]\s*$', re.MULTILINE)

# Pattern for markdown headings
HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def extract_reference_ids(content: str) -> list[tuple[str, int]]:
    """
    Extract r[...] IDs from Reference markdown content.
    
    Returns list of (id, position) tuples.
    """
    return [(m.group(1), m.start()) for m in REFERENCE_ID_PATTERN.finditer(content)]


def parse_reference_content(content: str, chapter_title: str) -> list[Section]:
    """
    Parse Reference markdown content into sections with paragraphs.
    
    Uses r[...] markers to define paragraph boundaries.
    Each r[...] marker starts a new paragraph that extends until the next marker.
    
    Args:
        content: Markdown content of the chapter file
        chapter_title: Title of the chapter (for context)
    
    Returns:
        List of sections with paragraphs
    """
    sections = []
    
    # Find all r[...] markers with positions
    id_matches = list(REFERENCE_ID_PATTERN.finditer(content))
    
    if not id_matches:
        # No markers - treat whole content as one section
        return [Section(
            id=_make_synthetic_id(chapter_title),
            title=chapter_title,
            level=1,
            content=_clean_markdown(content),
            paragraphs=[Paragraph(
                id=_make_synthetic_id(chapter_title, "p1"),
                text=_clean_markdown(content),
                heading_context=chapter_title,
            )],
        )]
    
    # Track current heading context
    current_heading = chapter_title
    current_heading_level = 1
    
    # Find all headings for context tracking
    headings = [(m.start(), len(m.group(1)), m.group(2).strip()) 
                for m in HEADING_PATTERN.finditer(content)]
    
    # Process each r[...] marker
    current_section: Section | None = None
    
    for i, match in enumerate(id_matches):
        marker_id = match.group(1)
        marker_pos = match.end()
        
        # Find next marker position (or end of content)
        if i + 1 < len(id_matches):
            next_pos = id_matches[i + 1].start()
        else:
            next_pos = len(content)
        
        # Extract text between this marker and the next
        text = content[marker_pos:next_pos].strip()
        
        # Update heading context based on position
        for h_pos, h_level, h_title in headings:
            if h_pos < marker_pos:
                current_heading = h_title
                current_heading_level = h_level
        
        # Check if this is a section-level ID (typically before a heading)
        # Section IDs are shorter (e.g., "type.pointer") vs paragraph IDs (e.g., "type.pointer.intro")
        is_section = marker_id.count('.') <= 1 or text.startswith('#')
        
        if is_section:
            # Extract section title from following heading if present
            section_title = current_heading
            heading_match = HEADING_PATTERN.match(text)
            if heading_match:
                section_title = heading_match.group(2).strip()
                text = text[heading_match.end():].strip()
            
            # Start a new section
            if current_section:
                sections.append(current_section)
            
            current_section = Section(
                id=marker_id,
                title=section_title,
                level=current_heading_level,
                content="",  # Will accumulate
                paragraphs=[],
            )
        
        # Add paragraph to current section
        if current_section:
            cleaned_text = _clean_markdown(text)
            if cleaned_text:
                current_section.paragraphs.append(Paragraph(
                    id=marker_id,
                    text=cleaned_text,
                    heading_context=current_heading,
                ))
                current_section.content += cleaned_text + "\n\n"
    
    # Don't forget the last section
    if current_section:
        sections.append(current_section)
    
    return sections


# =============================================================================
# UCG/Nomicon Parsing (Heading-based)
# =============================================================================

# Pattern for markdown anchor definitions: [anchor]: #anchor-text
ANCHOR_PATTERN = re.compile(r'^\[([^\]]+)\]:\s*#([a-z0-9-]+)', re.MULTILINE)


def extract_markdown_anchors(content: str) -> dict[str, str]:
    """
    Extract markdown anchor definitions from content.
    
    Returns dict mapping anchor name to anchor slug.
    E.g., {"abi": "abi-of-a-type"}
    """
    return {m.group(1): m.group(2) for m in ANCHOR_PATTERN.finditer(content)}


def parse_heading_based_content(
    content: str, 
    chapter_title: str,
    id_prefix: str,
) -> list[Section]:
    """
    Parse markdown content using headings to define sections.
    
    Used for UCG and Nomicon which don't have r[...] markers.
    Generates synthetic IDs from headings.
    
    Args:
        content: Markdown content
        chapter_title: Chapter title for context
        id_prefix: Prefix for generated IDs (e.g., "ucg", "nomicon")
    
    Returns:
        List of sections with paragraphs
    """
    sections = []
    
    # Split content by headings
    # Pattern captures heading level, title, and following content
    parts = re.split(r'^(#{1,6})\s+(.+)$', content, flags=re.MULTILINE)
    
    # parts will be: [preamble, #, title, content, ##, title, content, ...]
    
    current_section: Section | None = None
    preamble = parts[0].strip() if parts else ""
    
    # Handle preamble (content before first heading)
    if preamble:
        section_id = _make_synthetic_id(id_prefix, chapter_title)
        current_section = Section(
            id=section_id,
            title=chapter_title,
            level=1,
            content=_clean_markdown(preamble),
            paragraphs=[],
        )
        # Split preamble into paragraphs
        for i, para in enumerate(_split_into_paragraphs(preamble)):
            current_section.paragraphs.append(Paragraph(
                id=f"{section_id}_p{i+1}",
                text=para,
                heading_context=chapter_title,
            ))
        sections.append(current_section)
    
    # Process heading/content pairs
    i = 1
    while i < len(parts) - 2:
        level_str = parts[i]
        title = parts[i + 1].strip()
        content_block = parts[i + 2].strip() if i + 2 < len(parts) else ""
        i += 3
        
        level = len(level_str)
        section_id = _make_synthetic_id(id_prefix, title)
        
        section = Section(
            id=section_id,
            title=title,
            level=level,
            content=_clean_markdown(content_block),
            paragraphs=[],
        )
        
        # Split content into paragraphs
        for j, para in enumerate(_split_into_paragraphs(content_block)):
            section.paragraphs.append(Paragraph(
                id=f"{section_id}_p{j+1}",
                text=para,
                heading_context=title,
            ))
        
        sections.append(section)
    
    return sections


# =============================================================================
# Utility Functions
# =============================================================================

def _make_synthetic_id(*parts: str) -> str:
    """
    Generate a synthetic ID from parts.
    
    Converts to lowercase, replaces spaces/special chars with underscores.
    E.g., ("ucg", "Abstract Byte") -> "ucg_abstract_byte"
    """
    combined = "_".join(parts)
    # Lowercase, replace non-alphanumeric with underscore, collapse multiples
    result = re.sub(r'[^a-z0-9]+', '_', combined.lower())
    return result.strip('_')


def _clean_markdown(text: str) -> str:
    """
    Clean markdown text for embedding.
    
    - Removes r[...] markers
    - Removes code fence markers (but keeps code content)
    - Removes link syntax but keeps link text
    - Normalizes whitespace
    """
    # Remove r[...] markers
    text = REFERENCE_ID_PATTERN.sub('', text)
    
    # Remove code fence markers but keep content
    text = re.sub(r'^```\w*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```$', '', text, flags=re.MULTILINE)
    
    # Convert links [text](url) to just text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove reference-style links [text][ref]
    text = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', text)
    
    # Remove anchor definitions
    text = ANCHOR_PATTERN.sub('', text)
    
    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    return text


def _split_into_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs (separated by blank lines).
    
    Returns list of non-empty paragraphs.
    """
    paragraphs = re.split(r'\n\s*\n', text)
    return [_clean_markdown(p) for p in paragraphs if p.strip()]


def iter_markdown_files(src_dir: Path) -> Iterator[tuple[Path, str]]:
    """
    Iterate over all markdown files in a directory.
    
    Yields (path, content) tuples.
    Skips SUMMARY.md.
    """
    for md_file in sorted(src_dir.rglob("*.md")):
        if md_file.name == "SUMMARY.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        yield md_file, content
