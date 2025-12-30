#!/usr/bin/env python3
"""
Extract full text from MISRA C:2025 PDF for embedding generation.

This script parses the MISRA C:2025 PDF and extracts the complete text
for each rule and directive, including:
- Title
- Category (Required/Advisory/Mandatory)
- Analysis type
- Applies to (C90/C99/C11)
- Amplification
- Rationale
- Examples (code samples)
- Exceptions
- See also references

The extracted text is saved to cache/ (gitignored) because MISRA content
is copyrighted and should not be committed to version control.

Usage:
    uv run python tools/embeddings/extract_misra_text.py

Output:
    cache/misra_c_extracted_text.json
"""

import json
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def load_expected_guidelines(project_root: Path) -> list[dict]:
    """Load the list of expected guideline IDs from the standards file."""
    standards_path = project_root / "coding-standards-fls-mapping" / "standards" / "misra_c_2025.json"
    with open(standards_path, encoding="utf-8") as f:
        data = json.load(f)
    
    guidelines = []
    for category in data["categories"]:
        for g in category.get("guidelines", []):
            guidelines.append({
                "id": g["id"],
                "title": g.get("title", ""),
                "guideline_type": g.get("guideline_type", "rule"),
                "category_name": category.get("name", "")
            })
    return guidelines


def extract_pdf_text(pdf_path: Path, start_page: int = 0) -> str:
    """Extract text from PDF starting from a specific page."""
    reader = PdfReader(pdf_path)
    pages_text = []
    for i, page in enumerate(reader.pages):
        if i >= start_page:
            text = page.extract_text()
            if text:
                # Normalize non-breaking spaces
                text = text.replace('\xa0', ' ')
                pages_text.append(text)
    return '\n'.join(pages_text)


def build_guideline_pattern(guideline_id: str) -> str:
    """Build regex pattern for a guideline ID."""
    # Handle both "Rule X.Y" and "Dir X.Y"
    parts = guideline_id.split()
    if len(parts) != 2:
        return re.escape(guideline_id)
    
    prefix, number = parts
    # Allow flexible whitespace between prefix and number
    return rf'{re.escape(prefix)}\s+{re.escape(number)}'


def find_all_guideline_positions(full_text: str, guidelines: list[dict]) -> list[tuple[str, int, str, str]]:
    """
    Find all positions where guideline definitions start.
    Returns list of (guideline_id, position, title_text, category).
    
    A definition is identified by the pattern:
    Rule/Dir X.Y <title text>
    [optional reference annotations]
    Category Required/Advisory/Mandatory
    """
    positions = []
    
    # Build combined pattern for all guidelines
    # Look for: Rule/Dir X.Y followed by text, eventually followed by Category
    for g in guidelines:
        gid = g["id"]
        pattern = build_guideline_pattern(gid)
        
        # Pattern: guideline ID at start of line, followed by title text
        # The title may span multiple lines before "Category"
        # Category can be: Required, Advisory, Mandatory, or Disapplied
        # We require "Analysis" or "Applies to" after Category to distinguish from cross-references
        # Title must NOT start with:
        # - Section number (like "4.2" or "5.3")
        # - "Section" (page headers like "Section 5: Rules")
        # - "Rule" or "Dir" (another guideline)
        full_pattern = rf'(?:^|\n)({pattern})\s+(?!(?:\d+\.\d+|Section|Rule|Dir)\s)([^\n]+(?:\n(?!Category)[^\n]+)*)\n(?:\[[^\]]+\]\n)*Category\s+(Required|Advisory|Mandatory|Disapplied)\n(?:Analysis|Applies to)'
        
        for match in re.finditer(full_pattern, full_text, re.MULTILINE):
            gid_found = match.group(1).replace('  ', ' ').strip()
            # Normalize the found ID
            gid_normalized = re.sub(r'\s+', ' ', gid_found)
            title = match.group(2).strip()
            category = match.group(3)
            
            positions.append((gid_normalized, match.start(), title, category))
    
    # Sort by position
    positions.sort(key=lambda x: x[1])
    
    return positions


def extract_guideline_content(full_text: str, start_pos: int, end_pos: int) -> str:
    """Extract the content of a guideline between start and end positions."""
    content = full_text[start_pos:end_pos].strip()
    
    # Clean up page headers/footers
    content = re.sub(r'Section \d+: (?:Rules|Directives)\n\d+\n', '', content)
    content = re.sub(r'Licensed to:.*?\d{4}\n', '', content)
    content = re.sub(r'\n\d+\n', '\n', content)  # Page numbers
    
    return content.strip()


def parse_guideline_fields(guideline_id: str, content: str, title: str, category: str) -> dict:
    """Parse the extracted content into structured fields."""
    result = {
        "guideline_id": guideline_id,
        "title": title,
        "category": category,
        "analysis": "",
        "applies_to": "",
        "amplification": "",
        "rationale": "",
        "exceptions": "",
        "examples": "",
        "see_also": "",
        "full_text": content
    }
    
    if not content:
        return result
    
    # Extract Analysis type
    analysis_match = re.search(r'Analysis\s+([^\n]+)', content)
    if analysis_match:
        result["analysis"] = analysis_match.group(1).strip()
    
    # Extract Applies to
    applies_match = re.search(r'Applies to\s+([^\n]+)', content)
    if applies_match:
        result["applies_to"] = applies_match.group(1).strip()
    
    # Define section headers
    section_headers = [
        ("Amplification", "amplification"),
        ("Rationale", "rationale"), 
        ("Exception", "exceptions"),
        ("Example", "examples"),
        ("See also", "see_also")
    ]
    
    for header, field in section_headers:
        # Find where this section starts (header followed by newline)
        header_pattern = rf'\n{header}s?\s*\n'
        header_match = re.search(header_pattern, content, re.IGNORECASE)
        
        if header_match:
            start = header_match.end()
            
            # Find where next section starts
            end = len(content)
            for next_header, _ in section_headers:
                if next_header == header:
                    continue
                next_pattern = rf'\n{next_header}s?\s*\n'
                next_match = re.search(next_pattern, content[start:], re.IGNORECASE)
                if next_match:
                    potential_end = start + next_match.start()
                    if potential_end < end:
                        end = potential_end
            
            result[field] = content[start:end].strip()
    
    return result


def main():
    """Main extraction function."""
    project_root = get_project_root()
    pdf_path = project_root / "cache" / "misra-standards" / "MISRA-C-2025.pdf"
    output_path = project_root / "cache" / "misra_c_extracted_text.json"
    
    if not pdf_path.exists():
        print(f"Error: MISRA PDF not found at {pdf_path}")
        return 1
    
    # Load expected guidelines
    print("Loading expected guideline IDs...")
    expected_guidelines = load_expected_guidelines(project_root)
    print(f"Expected {len(expected_guidelines)} guidelines")
    
    # Extract PDF text starting from page 20 (before directives start)
    # Directives are in Section 4 (around page 22), Rules in Section 5 (around page 46)
    print(f"Reading PDF: {pdf_path}")
    full_text = extract_pdf_text(pdf_path, start_page=20)
    print(f"Extracted {len(full_text)} characters from rules/directives sections")
    
    # Find all guideline definition positions
    print("Finding guideline definitions...")
    positions = find_all_guideline_positions(full_text, expected_guidelines)
    print(f"Found {len(positions)} guideline definitions")
    
    # Create lookup from expected guidelines
    expected_lookup = {g["id"]: g for g in expected_guidelines}
    
    # Extract each guideline's content
    print("Extracting guideline content...")
    extracted_guidelines = []
    found_ids = set()
    
    for i, (gid, start_pos, title, category) in enumerate(positions):
        # Normalize guideline ID for lookup
        gid_normalized = gid.replace('  ', ' ').strip()
        
        # Skip duplicates (keep first occurrence which should be the definition)
        if gid_normalized in found_ids:
            continue
        found_ids.add(gid_normalized)
        
        # Find end position (start of next guideline or end of text)
        if i + 1 < len(positions):
            end_pos = positions[i + 1][1]
        else:
            end_pos = len(full_text)
        
        # Extract content
        content = extract_guideline_content(full_text, start_pos, end_pos)
        
        # Parse fields
        parsed = parse_guideline_fields(gid_normalized, content, title, category)
        
        # Add metadata from expected
        expected = expected_lookup.get(gid_normalized, {})
        parsed["guideline_type"] = expected.get("guideline_type", 
            "directive" if gid_normalized.startswith("Dir") else "rule")
        parsed["category_name"] = expected.get("category_name", "")
        
        extracted_guidelines.append(parsed)
    
    # Sort by guideline ID
    def sort_key(g):
        gid = g["guideline_id"]
        parts = gid.split()
        prefix = 0 if parts[0] == "Dir" else 1
        num_parts = parts[1].split(".")
        return (prefix, int(num_parts[0]), int(num_parts[1]))
    
    extracted_guidelines.sort(key=sort_key)
    
    # Find missing guidelines
    found_normalized = {g["guideline_id"] for g in extracted_guidelines}
    missing = []
    for expected in expected_guidelines:
        if expected["id"] not in found_normalized:
            missing.append(expected["id"])
    
    # Validate counts
    rules = [g for g in extracted_guidelines if g["guideline_type"] == "rule"]
    directives = [g for g in extracted_guidelines if g["guideline_type"] == "directive"]
    with_rationale = [g for g in extracted_guidelines if g["rationale"]]
    with_category = [g for g in extracted_guidelines if g["category"]]
    
    print(f"\nExtraction Summary:")
    print(f"  Total extracted: {len(extracted_guidelines)}")
    print(f"  Rules: {len(rules)}")
    print(f"  Directives: {len(directives)}")
    print(f"  With rationale: {len(with_rationale)}")
    print(f"  With category: {len(with_category)}")
    print(f"  Missing: {len(missing)}")
    
    if missing:
        print(f"\nMissing guidelines:")
        for m in missing[:20]:
            print(f"  - {m}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
    
    # If we don't have all 212, try to add the missing ones with empty content
    if len(extracted_guidelines) < 212:
        print(f"\nAdding {len(missing)} missing guidelines with empty content...")
        for m in missing:
            expected = expected_lookup.get(m, {})
            extracted_guidelines.append({
                "guideline_id": m,
                "title": expected.get("title", ""),
                "category": "",
                "analysis": "",
                "applies_to": "",
                "amplification": "",
                "rationale": "",
                "exceptions": "",
                "examples": "",
                "see_also": "",
                "full_text": "",
                "guideline_type": expected.get("guideline_type", "rule"),
                "category_name": expected.get("category_name", ""),
                "_extraction_note": "Content not found in PDF - may need manual extraction"
            })
        
        # Re-sort
        extracted_guidelines.sort(key=sort_key)
    
    # Final counts
    rules = [g for g in extracted_guidelines if g["guideline_type"] == "rule"]
    directives = [g for g in extracted_guidelines if g["guideline_type"] == "directive"]
    
    # Create output structure
    output = {
        "source": "MISRA-C-2025.pdf",
        "extraction_date": str(date.today()),
        "statistics": {
            "total_guidelines": len(extracted_guidelines),
            "rules": len(rules),
            "directives": len(directives),
            "with_rationale": len([g for g in extracted_guidelines if g["rationale"]]),
            "with_category": len([g for g in extracted_guidelines if g["category"]]),
            "missing_content": len([g for g in extracted_guidelines if not g["full_text"]])
        },
        "guidelines": extracted_guidelines,
        "_copyright_notice": "This file contains copyrighted MISRA content. DO NOT COMMIT TO VERSION CONTROL."
    }
    
    # Validate final counts
    if len(extracted_guidelines) != 212:
        print(f"\nERROR: Expected 212 guidelines, got {len(extracted_guidelines)}")
    
    if len(rules) != 190:
        print(f"\nWARNING: Expected 190 rules, got {len(rules)}")
        
    if len(directives) != 22:
        print(f"\nWARNING: Expected 22 directives, got {len(directives)}")
    
    # Ensure cache directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to: {output_path}")
    
    # Show samples
    print("\nSample extractions:")
    for sample_id in ["Dir 4.1", "Rule 1.1", "Rule 11.1", "Rule 18.1"]:
        for g in extracted_guidelines:
            if g["guideline_id"] == sample_id:
                print(f"\n{sample_id}:")
                title_preview = g['title'][:60] + "..." if len(g['title']) > 60 else g['title']
                print(f"  Title: {title_preview}")
                print(f"  Category: {g['category']}")
                print(f"  Rationale: {len(g['rationale'])} chars")
                print(f"  Full text: {len(g['full_text'])} chars")
                break
    
    return 0


if __name__ == "__main__":
    exit(main())
