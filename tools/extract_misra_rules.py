#!/usr/bin/env -S uv run python
"""
Extract rule and directive titles from MISRA C and MISRA C++ PDFs.

This script extracts only the rule/directive numbers and titles (not full content)
from MISRA standards PDFs for use in FLS mapping analysis.

Usage:
    uv run python tools/extract_misra_rules.py

Output:
    coding-standards-fls-mapping/standards/misra_c_2025.json
    coding-standards-fls-mapping/standards/misra_cpp_2023.json
"""

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
CACHE_DIR = ROOT_DIR / "cache" / "misra-standards"
OUTPUT_DIR = ROOT_DIR / "coding-standards-fls-mapping" / "standards"

# PDF file names
MISRA_C_PDF = "MISRA-C-2025.pdf"
MISRA_CPP_PDF = "MISRA-CPP-2023-PDF-j3rs83.pdf"


@dataclass
class Guideline:
    """A single rule or directive."""

    id: str
    title: str
    guideline_type: str  # "rule" or "directive"


@dataclass
class Category:
    """A category grouping related guidelines."""

    id: str
    name: str
    guidelines: list[Guideline]


def clean_title(title: str) -> str:
    """Clean up extracted title text."""
    # Remove line breaks and extra whitespace
    title = re.sub(r"\s+", " ", title.strip())
    # Remove trailing punctuation artifacts
    title = re.sub(r"[,;:]+$", "", title)
    # Remove source references like [ISO 26262-6 Section 9.4.5]
    title = re.sub(r"\s*\[.*?\]\s*$", "", title)
    return title.strip()


def extract_misra_c_guidelines(pdf_path: Path) -> tuple[list[Category], dict]:
    """Extract guidelines from MISRA C:2025 PDF."""
    reader = PdfReader(pdf_path)
    guidelines_by_section: dict[str, list[Guideline]] = defaultdict(list)

    # Section names from MISRA C:2025 TOC
    section_names = {
        "1": "A standard C environment",
        "2": "Unused code",
        "3": "Comments",
        "4": "Character sets and lexical conventions",
        "5": "Identifiers",
        "6": "Types",
        "7": "Literals and constants",
        "8": "Declarations and definitions",
        "9": "Initialization",
        "10": "The essential type model",
        "11": "Pointer type conversions",
        "12": "Expressions",
        "13": "Side effects",
        "14": "Control statement expressions",
        "15": "Control flow",
        "16": "Switch statements",
        "17": "Functions",
        "18": "Pointers and arrays",
        "19": "Overlapping storage",
        "20": "Preprocessing directives",
        "21": "Standard libraries",
        "22": "Resources",
        "23": "Concurrency",
    }

    # Directive section names
    directive_section_names = {
        "1": "The implementation",
        "2": "Compilation and build",
        "3": "Requirements traceability",
        "4": "Code design",
        "5": "Concurrency considerations",
    }

    # Pattern for rules: "Rule X.Y title"
    # Pattern for directives: "Dir X.Y title"
    rule_pattern = re.compile(
        r"^Rule\s+(\d+)\.(\d+)\s+(.+?)$", re.MULTILINE
    )
    dir_pattern = re.compile(
        r"^Dir\s+(\d+)\.(\d+)\s+(.+?)$", re.MULTILINE
    )

    seen_rules = set()
    seen_dirs = set()

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue

        # Extract rules
        for match in rule_pattern.finditer(text):
            section = match.group(1)
            rule_num = match.group(2)
            title = match.group(3)
            rule_id = f"Rule {section}.{rule_num}"

            if rule_id in seen_rules:
                continue
            seen_rules.add(rule_id)

            title = clean_title(title)
            if not title or len(title) < 5:
                continue

            # Skip if title looks like a cross-reference
            if title.startswith("Rule ") or title.startswith("Dir "):
                continue

            guidelines_by_section[f"rule_{section}"].append(
                Guideline(id=rule_id, title=title, guideline_type="rule")
            )

        # Extract directives
        for match in dir_pattern.finditer(text):
            section = match.group(1)
            dir_num = match.group(2)
            title = match.group(3)
            dir_id = f"Dir {section}.{dir_num}"

            if dir_id in seen_dirs:
                continue
            seen_dirs.add(dir_id)

            title = clean_title(title)
            if not title or len(title) < 5:
                continue

            # Skip if title looks like a cross-reference
            if title.startswith("Rule ") or title.startswith("Dir "):
                continue

            guidelines_by_section[f"dir_{section}"].append(
                Guideline(id=dir_id, title=title, guideline_type="directive")
            )

    # Build categories
    categories = []

    # Add directive categories first
    for section_num in sorted(directive_section_names.keys()):
        key = f"dir_{section_num}"
        if key in guidelines_by_section:
            guidelines = sorted(
                guidelines_by_section[key],
                key=lambda g: (int(g.id.split()[1].split(".")[0]), int(g.id.split()[1].split(".")[1])),
            )
            categories.append(
                Category(
                    id=f"Dir {section_num}",
                    name=directive_section_names[section_num],
                    guidelines=guidelines,
                )
            )

    # Add rule categories
    for section_num in sorted(section_names.keys(), key=int):
        key = f"rule_{section_num}"
        if key in guidelines_by_section:
            guidelines = sorted(
                guidelines_by_section[key],
                key=lambda g: (int(g.id.split()[1].split(".")[0]), int(g.id.split()[1].split(".")[1])),
            )
            categories.append(
                Category(
                    id=f"Rule {section_num}",
                    name=section_names[section_num],
                    guidelines=guidelines,
                )
            )

    # Compute statistics
    total_rules = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "rule"
    )
    total_dirs = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "directive"
    )
    stats = {
        "total_guidelines": total_rules + total_dirs,
        "rules": total_rules,
        "directives": total_dirs,
        "recommendations": 0,
        "categories": len(categories),
    }

    return categories, stats


def extract_misra_cpp_guidelines(pdf_path: Path) -> tuple[list[Category], dict]:
    """Extract guidelines from MISRA C++:2023 PDF."""
    reader = PdfReader(pdf_path)
    guidelines_by_section: dict[str, list[Guideline]] = defaultdict(list)

    # Section names from MISRA C++:2023 TOC (section 4.x)
    section_names = {
        "0": "Language independent issues",
        "4": "General principles",
        "5": "Lexical conventions",
        "6": "Basic concepts",
        "7": "Standard conversions",
        "8": "Expressions",
        "9": "Statements",
        "10": "Declarations",
        "11": "Declarators",
        "12": "Classes",
        "13": "Derived classes",
        "14": "Member access control",
        "15": "Special member functions",
        "16": "Overloading",
        "17": "Templates",
        "18": "Exception handling",
        "19": "Preprocessing directives",
        "21": "Standard library",
        "26": "Concurrency",
        "28": "Appendix B: Library support",
        "30": "Appendix D: Compatibility features",
    }

    # MISRA C++ uses three-part numbering: Rule/Dir X.Y.Z
    rule_pattern = re.compile(
        r"^Rule\s+(\d+)\.(\d+)\.(\d+)\s+(.+?)$", re.MULTILINE
    )
    dir_pattern = re.compile(
        r"^Dir\s+(\d+)\.(\d+)\.(\d+)\s+(.+?)$", re.MULTILINE
    )

    seen_rules = set()
    seen_dirs = set()

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue

        # Extract rules
        for match in rule_pattern.finditer(text):
            section = match.group(1)
            subsection = match.group(2)
            rule_num = match.group(3)
            title = match.group(4)
            rule_id = f"Rule {section}.{subsection}.{rule_num}"

            if rule_id in seen_rules:
                continue
            seen_rules.add(rule_id)

            title = clean_title(title)
            if not title or len(title) < 5:
                continue

            # Skip if title looks like a cross-reference
            if title.startswith("Rule ") or title.startswith("Dir "):
                continue

            guidelines_by_section[f"rule_{section}"].append(
                Guideline(id=rule_id, title=title, guideline_type="rule")
            )

        # Extract directives
        for match in dir_pattern.finditer(text):
            section = match.group(1)
            subsection = match.group(2)
            dir_num = match.group(3)
            title = match.group(4)
            dir_id = f"Dir {section}.{subsection}.{dir_num}"

            if dir_id in seen_dirs:
                continue
            seen_dirs.add(dir_id)

            title = clean_title(title)
            if not title or len(title) < 5:
                continue

            # Skip if title looks like a cross-reference
            if title.startswith("Rule ") or title.startswith("Dir "):
                continue

            guidelines_by_section[f"dir_{section}"].append(
                Guideline(id=dir_id, title=title, guideline_type="directive")
            )

    # Build categories
    categories = []
    all_sections = set()

    for key in guidelines_by_section:
        section_num = key.split("_")[1]
        all_sections.add(section_num)

    for section_num in sorted(all_sections, key=lambda x: int(x)):
        section_name = section_names.get(section_num, f"Section {section_num}")

        # Combine rules and directives for this section
        all_guidelines = []
        if f"dir_{section_num}" in guidelines_by_section:
            all_guidelines.extend(guidelines_by_section[f"dir_{section_num}"])
        if f"rule_{section_num}" in guidelines_by_section:
            all_guidelines.extend(guidelines_by_section[f"rule_{section_num}"])

        if all_guidelines:
            # Sort by full ID
            all_guidelines.sort(
                key=lambda g: tuple(
                    int(x) for x in g.id.split()[1].split(".")
                )
            )
            categories.append(
                Category(
                    id=f"Section {section_num}",
                    name=section_name,
                    guidelines=all_guidelines,
                )
            )

    # Compute statistics
    total_rules = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "rule"
    )
    total_dirs = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "directive"
    )
    stats = {
        "total_guidelines": total_rules + total_dirs,
        "rules": total_rules,
        "directives": total_dirs,
        "recommendations": 0,
        "categories": len(categories),
    }

    return categories, stats


def categories_to_dict(categories: list[Category]) -> list[dict]:
    """Convert Category objects to JSON-serializable dicts."""
    return [
        {
            "id": cat.id,
            "name": cat.name,
            "guidelines": [
                {
                    "id": g.id,
                    "title": g.title,
                    "guideline_type": g.guideline_type,
                }
                for g in cat.guidelines
            ],
        }
        for cat in categories
    ]


def main():
    """Extract MISRA rules from PDFs and save to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Extract MISRA C:2025
    misra_c_path = CACHE_DIR / MISRA_C_PDF
    if misra_c_path.exists():
        print(f"Extracting from {MISRA_C_PDF}...")
        categories, stats = extract_misra_c_guidelines(misra_c_path)

        output = {
            "standard": "MISRA-C",
            "version": "2025",
            "extraction_date": date.today().isoformat(),
            "source": MISRA_C_PDF,
            "statistics": stats,
            "categories": categories_to_dict(categories),
        }

        output_path = OUTPUT_DIR / "misra_c_2025.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"  Extracted {stats['rules']} rules, {stats['directives']} directives")
        print(f"  Saved to {output_path}")
    else:
        print(f"Warning: {misra_c_path} not found")

    # Extract MISRA C++:2023
    misra_cpp_path = CACHE_DIR / MISRA_CPP_PDF
    if misra_cpp_path.exists():
        print(f"\nExtracting from {MISRA_CPP_PDF}...")
        categories, stats = extract_misra_cpp_guidelines(misra_cpp_path)

        output = {
            "standard": "MISRA-C++",
            "version": "2023",
            "extraction_date": date.today().isoformat(),
            "source": MISRA_CPP_PDF,
            "statistics": stats,
            "categories": categories_to_dict(categories),
        }

        output_path = OUTPUT_DIR / "misra_cpp_2023.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

        print(f"  Extracted {stats['rules']} rules, {stats['directives']} directives")
        print(f"  Saved to {output_path}")
    else:
        print(f"Warning: {misra_cpp_path} not found")

    print("\nDone!")


if __name__ == "__main__":
    main()
