#!/usr/bin/env python3
"""
extract-clippy-lints: Extract Clippy lint definitions to JSON.

Parses `declare_clippy_lint!` macro invocations from Clippy source to extract
lint names, categories, and documentation.

Usage:
    uv run extract-clippy-lints              # Extract all lints
    uv run extract-clippy-lints --force      # Re-extract even if exists

Output:
    embeddings/clippy/index.json
    embeddings/clippy/lints.json
"""

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fls_tools.shared import get_project_root, get_cache_dir, get_embeddings_dir


@dataclass
class ClippyLint:
    """Represents a Clippy lint definition."""
    name: str  # e.g., "APPROX_CONSTANT"
    snake_name: str  # e.g., "approx_constant"
    category: str  # e.g., "correctness"
    brief: str  # Brief description
    what_it_does: str  # From "### What it does"
    why_bad: str  # From "### Why is this bad?" or "### Why restrict this?"
    example: str  # Code example
    version: str  # Clippy version when introduced
    source_file: str  # Source file path


# Clippy lint categories with their search weights
CATEGORY_WEIGHTS = {
    "correctness": 1.2,  # Higher weight - safety critical
    "suspicious": 1.15,  # Often catches real bugs
    "restriction": 1.0,
    "pedantic": 1.0,
    "style": 0.95,
    "complexity": 1.0,
    "perf": 1.0,
    "cargo": 0.9,
    "nursery": 0.9,  # Lower weight - not yet stable
}


def get_clippy_src_dir(root: Path) -> Path:
    """Get the Clippy lints source directory."""
    return get_cache_dir(root) / "docs" / "rust-clippy" / "clippy_lints" / "src"


def get_clippy_output_dir(root: Path) -> Path:
    """Get the Clippy embeddings output directory."""
    return get_embeddings_dir(root) / "clippy"


def parse_lint_macro(content: str) -> list[ClippyLint]:
    """
    Parse all declare_clippy_lint! macros in file content.
    
    Returns list of parsed lints.
    """
    lints = []
    
    # Pattern to match entire declare_clippy_lint! { ... } blocks
    # This is tricky because the macro body contains nested braces in code examples
    # We'll use a simpler approach: find each macro start and then count braces
    
    macro_pattern = re.compile(r'declare_clippy_lint!\s*\{')
    
    for match in macro_pattern.finditer(content):
        start = match.start()
        
        # Find matching closing brace
        brace_count = 1
        pos = match.end()
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        if brace_count == 0:
            macro_body = content[match.end():pos-1]
            lint = parse_lint_body(macro_body)
            if lint:
                lints.append(lint)
    
    return lints


def parse_lint_body(body: str) -> ClippyLint | None:
    """
    Parse the body of a declare_clippy_lint! macro.
    
    Expected format:
        /// ### What it does
        /// Description...
        ///
        /// ### Why is this bad?
        /// Reason...
        ///
        /// ### Example
        /// ```
        /// code
        /// ```
        #[clippy::version = "1.0.0"]
        pub LINT_NAME,
        category,
        "brief description"
    """
    # Extract doc comments
    doc_lines = []
    for line in body.split('\n'):
        line = line.strip()
        if line.startswith('///'):
            doc_lines.append(line[3:].strip())
    
    doc_text = '\n'.join(doc_lines)
    
    # Parse sections
    what_it_does = extract_doc_section(doc_text, "What it does")
    why_bad = extract_doc_section(doc_text, "Why is this bad") or \
              extract_doc_section(doc_text, "Why restrict this")
    example = extract_doc_section(doc_text, "Example")
    
    # Extract version
    version_match = re.search(r'#\[clippy::version\s*=\s*"([^"]+)"\]', body)
    version = version_match.group(1) if version_match else "unknown"
    
    # Extract lint name and category
    # Pattern: pub LINT_NAME,\n    category,\n    "description"
    name_pattern = re.compile(
        r'pub\s+([A-Z][A-Z0-9_]+)\s*,\s*'
        r'([a-z_]+)\s*,\s*'
        r'"([^"]+)"',
        re.DOTALL
    )
    name_match = name_pattern.search(body)
    
    if not name_match:
        return None
    
    name = name_match.group(1)
    category = name_match.group(2)
    brief = name_match.group(3)
    
    return ClippyLint(
        name=name,
        snake_name=name.lower(),
        category=category,
        brief=brief,
        what_it_does=what_it_does or "",
        why_bad=why_bad or "",
        example=example or "",
        version=version,
        source_file="",  # Will be filled in later
    )


def extract_doc_section(doc_text: str, section_name: str) -> str | None:
    """
    Extract a doc section by name.
    
    Looks for "### Section Name" and extracts content until next "###" or end.
    """
    pattern = re.compile(
        rf'###\s+{re.escape(section_name)}[^\n]*\n(.*?)(?=###|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    match = pattern.search(doc_text)
    if match:
        content = match.group(1).strip()
        return content
    return None


def extract_lints_from_file(file_path: Path) -> list[ClippyLint]:
    """Extract all lints from a single source file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  Warning: Could not read {file_path}: {e}")
        return []
    
    lints = parse_lint_macro(content)
    
    # Set source file for each lint
    for lint in lints:
        lint.source_file = file_path.name
    
    return lints


def main():
    parser = argparse.ArgumentParser(
        description="Extract Clippy lint definitions to JSON"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-extract even if output exists",
    )
    
    args = parser.parse_args()
    root = get_project_root()
    
    src_dir = get_clippy_src_dir(root)
    output_dir = get_clippy_output_dir(root)
    
    if not src_dir.exists():
        print(f"ERROR: Clippy source not found at {src_dir}")
        print("Run: uv run clone-rust-docs --source clippy")
        return 1
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    lints_file = output_dir / "lints.json"
    if lints_file.exists() and not args.force:
        print(f"Output exists: {lints_file}")
        print("Use --force to re-extract")
        return 0
    
    # Find all .rs files in the lints directory
    print(f"Scanning {src_dir}...")
    
    all_lints = []
    category_counts: dict[str, int] = {}
    
    for rs_file in sorted(src_dir.rglob("*.rs")):
        # Skip test files and mod.rs files that just export
        if "test" in rs_file.name or rs_file.name == "lib.rs":
            continue
        
        lints = extract_lints_from_file(rs_file)
        if lints:
            print(f"  {rs_file.name}: {len(lints)} lint(s)")
            all_lints.extend(lints)
            
            for lint in lints:
                category_counts[lint.category] = category_counts.get(lint.category, 0) + 1
    
    # Convert to JSON format
    lints_data = []
    for lint in all_lints:
        lints_data.append({
            "id": f"clippy::{lint.snake_name}",
            "name": lint.name,
            "snake_name": lint.snake_name,
            "category": lint.category,
            "weight": CATEGORY_WEIGHTS.get(lint.category, 1.0),
            "brief": lint.brief,
            "what_it_does": lint.what_it_does,
            "why_bad": lint.why_bad,
            "example": lint.example,
            "version": lint.version,
            "source_file": lint.source_file,
            # Combined text for embedding
            "embedding_text": f"{lint.brief}\n\n{lint.what_it_does}\n\n{lint.why_bad}".strip(),
        })
    
    # Save lints
    with open(lints_file, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Clippy",
            "source_repo": "https://github.com/rust-lang/rust-clippy",
            "extraction_date": str(date.today()),
            "total_lints": len(lints_data),
            "categories": category_counts,
            "category_weights": CATEGORY_WEIGHTS,
            "lints": lints_data,
        }, f, indent=2)
        f.write("\n")
    print(f"\nSaved: {lints_file}")
    
    # Save index
    index_data = {
        "source": "Clippy",
        "source_repo": "https://github.com/rust-lang/rust-clippy",
        "extraction_date": str(date.today()),
        "total_lints": len(lints_data),
        "categories": category_counts,
        "category_weights": CATEGORY_WEIGHTS,
    }
    
    index_file = output_dir / "index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)
        f.write("\n")
    print(f"Saved: {index_file}")
    
    # Summary
    print(f"\n{'='*60}")
    print("EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Total lints: {len(lints_data)}")
    print("\nBy category:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        weight = CATEGORY_WEIGHTS.get(cat, 1.0)
        print(f"  {cat}: {count} (weight: {weight})")
    
    return 0


if __name__ == "__main__":
    exit(main())
