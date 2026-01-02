#!/usr/bin/env python3
"""
Extract MISRA C:2025 Addendum 6 (Rust Applicability) data from PDF.

This script parses the MISRA ADD-6 PDF and extracts the complete
Guideline-by-Guideline table including all columns:
- Guideline ID
- MISRA Category (Required/Advisory/Mandatory)
- Decidability (Decidable/Undecidable)
- Scope (STU/System)
- Rationale (UB, IDB, CQ, DC - can be multiple)
- Applicability (all Rust)
- Applicability (safe Rust)
- Adjusted Category
- Comment

It also extracts the definition tables from Section 2.

Usage:
    uv run extract-misra-add6

Output:
    coding-standards-fls-mapping/misra_rust_applicability.json
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from fls_tools.shared import get_project_root


# Valid values for validation
VALID_MISRA_CATEGORIES = {"Required", "Advisory", "Mandatory"}
VALID_DECIDABILITY = {"Decidable", "Undecidable", "n/a"}
VALID_SCOPE = {"STU", "System", "n/a"}
VALID_RATIONALE = {"UB", "IDB", "CQ", "DC"}
VALID_APPLICABILITY = {"Yes", "No", "Partial"}
VALID_ADJUSTED_CATEGORY = {"Required", "Advisory", "Recommended", "Disapplied", "Implicit", "N/A"}


def get_add6_pdf_path(root: Path) -> Path:
    """Get path to ADD-6 PDF."""
    return root / "cache" / "misra-standards" / "MISRA-C-2025-ADD-6_Rust-Applicabiliity.pdf"


def get_output_path(root: Path) -> Path:
    """Get output path for applicability JSON."""
    return root / "coding-standards-fls-mapping" / "misra_rust_applicability.json"


def normalize_guideline_id(raw_id: str) -> str:
    """
    Normalize guideline ID from PDF format to our format.
    
    Examples:
        "D.1.1" -> "Dir 1.1"
        "R.22.8" -> "Rule 22.8"
    """
    raw_id = raw_id.strip()
    if raw_id.startswith("D."):
        return "Dir " + raw_id[2:]
    elif raw_id.startswith("R."):
        return "Rule " + raw_id[2:]
    return raw_id


def parse_rationale(rationale_str: str) -> list[str]:
    """
    Parse rationale string into list of values.
    
    Examples:
        "UB" -> ["UB"]
        "UB, IDB" -> ["UB", "IDB"]
        "UB, DC" -> ["UB", "DC"]
    """
    if not rationale_str or rationale_str.strip() == "":
        return []
    
    # Split on comma and clean up
    parts = [p.strip() for p in rationale_str.split(",")]
    # Filter to valid values only
    result = [p for p in parts if p in VALID_RATIONALE]
    return result


def parse_table_row(line: str) -> dict | None:
    """
    Parse a single row from the guideline table.
    
    Returns dict with parsed fields or None if not a valid row.
    """
    # Skip header rows and empty lines
    if not line.strip():
        return None
    if line.startswith("Guideline"):
        return None
    if line.startswith("MISRA C:2025"):
        return None
    if line.startswith("Category"):
        return None
    
    # Check if line starts with a guideline ID pattern (D.X.Y or R.X.Y)
    match = re.match(r'^([DR])\.(\d+)\.(\d+)\s+', line)
    if not match:
        return None
    
    # Handle "Renumbered" entries
    if "Renumbered" in line or "moved to" in line.lower():
        gid = normalize_guideline_id(f"{match.group(1)}.{match.group(2)}.{match.group(3)}")
        return {
            "guideline_id": gid,
            "renumbered": True,
            "comment": line[match.end():].strip()
        }
    
    # Parse the columns - this is tricky because columns are space-separated
    # and the Comment field can contain spaces
    #
    # Expected format:
    # R.22.8 Required Undecidable System DC Yes No Disapplied only accessible through unsafe extern "C"
    #
    # Columns: ID, Category, Decidability, Scope, Rationale, Applicability(all), Applicability(safe), AdjustedCategory, Comment
    
    rest = line[match.end():].strip()
    
    # Try to parse using known value patterns
    # Strategy: extract known values from left to right
    
    result = {
        "guideline_id": normalize_guideline_id(f"{match.group(1)}.{match.group(2)}.{match.group(3)}"),
        "misra_category": None,
        "decidability": None,
        "scope": None,
        "rationale": [],
        "applicability_all_rust": None,
        "applicability_safe_rust": None,
        "adjusted_category": None,
        "comment": ""
    }
    
    # Split into tokens
    tokens = rest.split()
    # Minimum tokens needed:
    # - For rules: Category, Decidability, Scope, Rationale, App_all, App_safe, AdjCat = 7
    # - For directives: Category, n/a, Rationale, App_all, App_safe, AdjCat = 6
    # Use 6 as minimum to allow directives
    if len(tokens) < 6:
        # Not enough tokens for a valid row
        return None
    
    idx = 0
    
    # MISRA Category (Required/Advisory/Mandatory)
    if idx < len(tokens) and tokens[idx] in VALID_MISRA_CATEGORIES:
        result["misra_category"] = tokens[idx]
        idx += 1
    else:
        return None
    
    # Decidability (Decidable/Undecidable/n/a)
    if idx < len(tokens) and tokens[idx] in VALID_DECIDABILITY:
        result["decidability"] = tokens[idx]
        idx += 1
        
        # For Directives, n/a is used for BOTH decidability and scope (single token)
        # For Rules, there are separate Decidability and Scope columns
        if result["decidability"] == "n/a":
            # Directives: n/a covers both, so set scope to n/a as well
            result["scope"] = "n/a"
        else:
            # Rules: need to parse separate Scope column
            if idx < len(tokens) and tokens[idx] in VALID_SCOPE:
                result["scope"] = tokens[idx]
                idx += 1
            else:
                return None
    else:
        return None
    
    # Rationale - can be multiple values separated by commas
    # This is tricky because "UB, IDB" becomes ["UB,", "IDB"] when split
    rationale_parts = []
    while idx < len(tokens):
        token = tokens[idx]
        # Check if it's a rationale value (possibly with comma)
        clean_token = token.rstrip(",")
        if clean_token in VALID_RATIONALE:
            rationale_parts.append(clean_token)
            idx += 1
            # If token didn't end with comma, we're done with rationale
            if not token.endswith(","):
                break
        else:
            break
    
    result["rationale"] = rationale_parts
    
    # Applicability (all Rust) - Yes/No/Partial
    if idx < len(tokens) and tokens[idx] in VALID_APPLICABILITY:
        result["applicability_all_rust"] = tokens[idx]
        idx += 1
    else:
        return None
    
    # Applicability (safe Rust) - Yes/No/Partial
    if idx < len(tokens) and tokens[idx] in VALID_APPLICABILITY:
        result["applicability_safe_rust"] = tokens[idx]
        idx += 1
    else:
        return None
    
    # Adjusted Category - Required/Advisory/Recommended/Disapplied/Implicit/N/A
    if idx < len(tokens):
        adj_cat = tokens[idx]
        if adj_cat in VALID_ADJUSTED_CATEGORY:
            result["adjusted_category"] = adj_cat.lower() if adj_cat != "N/A" else "n_a"
            idx += 1
        else:
            return None
    else:
        return None
    
    # Comment - rest of the tokens
    if idx < len(tokens):
        result["comment"] = " ".join(tokens[idx:])
    
    return result


def extract_guidelines_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract all guidelines from the ADD-6 PDF.
    
    Returns list of guideline dicts.
    """
    reader = PdfReader(pdf_path)
    guidelines = []
    seen_ids = set()
    
    # The guideline table spans pages 11-20 (0-indexed: 10-19)
    for page_num in range(10, 20):
        if page_num >= len(reader.pages):
            break
        
        page = reader.pages[page_num]
        text = page.extract_text()
        if not text:
            continue
        
        # Process line by line
        for line in text.split("\n"):
            parsed = parse_table_row(line)
            if parsed:
                gid = parsed["guideline_id"]
                # Skip duplicates (keep first occurrence)
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    guidelines.append(parsed)
    
    return guidelines


def build_output_structure(guidelines: list[dict]) -> dict:
    """
    Build the complete output JSON structure.
    """
    # Separate renumbered entries
    renumbered = [g for g in guidelines if g.get("renumbered")]
    regular = [g for g in guidelines if not g.get("renumbered")]
    
    # Build guidelines dict
    guidelines_dict = {}
    for g in regular:
        gid = g["guideline_id"]
        guidelines_dict[gid] = {
            "misra_category": g["misra_category"],
            "decidability": g["decidability"],
            "scope": g["scope"],
            "rationale": g["rationale"],
            "applicability_all_rust": g["applicability_all_rust"],
            "applicability_safe_rust": g["applicability_safe_rust"],
            "adjusted_category": g["adjusted_category"],
            "comment": g["comment"]
        }
    
    # Add renumbered entries with special handling
    for g in renumbered:
        gid = g["guideline_id"]
        guidelines_dict[gid] = {
            "renumbered": True,
            "comment": g["comment"]
        }
    
    return {
        "metadata": {
            "source": "MISRA C:2025 Addendum 6 - Applicability of MISRA C:2025 to the Rust Language",
            "version": "Working Draft March 2025",
            "isbn": "978-1-911700-22-7",
            "extracted_date": str(date.today()),
            "total_guidelines": len(guidelines_dict)
        },
        "applicability_values": {
            "Yes": "The MISRA C guideline applies equally to the Rust language",
            "No": "The MISRA C guideline does not apply to the Rust language",
            "Partial": "The MISRA C guideline partially applies to some aspects of the Rust language"
        },
        "adjusted_category_values": {
            "required": "Code shall comply with this guideline, with a formal deviation required where this is not the case",
            "advisory": "These are recommendations which should be followed as far as is reasonably practical",
            "recommended": "Best practice recommendations",
            "disapplied": "Guidelines for which compliance is not required. No enforcement is expected",
            "implicit": "The behaviour is not permitted by Rust (compiler enforces)",
            "n_a": "The behaviour does not apply to Rust"
        },
        "rationale_values": {
            "UB": "The MISRA C guideline applies to C Undefined Behaviour",
            "IDB": "The MISRA C guideline applies to C Implementation-defined Behaviour",
            "CQ": "The MISRA C guideline applies to Code Quality considerations",
            "DC": "The MISRA C guideline applies to Design Considerations"
        },
        "decidability_values": {
            "Decidable": "Can be checked by static analysis",
            "Undecidable": "Cannot be fully checked by static analysis",
            "n/a": "Not applicable"
        },
        "scope_values": {
            "STU": "Single Translation Unit - analysis confined to one compilation unit",
            "System": "Requires system-wide analysis across multiple compilation units",
            "n/a": "Not applicable"
        },
        "guidelines": guidelines_dict
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract MISRA C:2025 ADD-6 Rust Applicability data from PDF"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path (default: coding-standards-fls-mapping/misra_rust_applicability.json)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print extraction results without writing file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output"
    )
    args = parser.parse_args()
    
    root = get_project_root()
    pdf_path = get_add6_pdf_path(root)
    output_path = Path(args.output) if args.output else get_output_path(root)
    
    if not pdf_path.exists():
        print(f"Error: ADD-6 PDF not found at {pdf_path}")
        return 1
    
    print(f"Reading PDF: {pdf_path}")
    
    # Extract guidelines
    guidelines = extract_guidelines_from_pdf(pdf_path)
    
    # Build output structure
    output = build_output_structure(guidelines)
    
    # Statistics
    regular = [g for g in guidelines if not g.get("renumbered")]
    renumbered = [g for g in guidelines if g.get("renumbered")]
    
    print(f"\nExtraction Summary:")
    print(f"  Total entries: {len(guidelines)}")
    print(f"  Regular guidelines: {len(regular)}")
    print(f"  Renumbered entries: {len(renumbered)}")
    
    # Count by rationale type
    rationale_counts = {"UB": 0, "IDB": 0, "CQ": 0, "DC": 0}
    for g in regular:
        for r in g.get("rationale", []):
            if r in rationale_counts:
                rationale_counts[r] += 1
    
    print(f"\nRationale distribution:")
    for r, count in sorted(rationale_counts.items()):
        print(f"  {r}: {count}")
    
    # Count by adjusted category
    adj_cat_counts = {}
    for g in regular:
        cat = g.get("adjusted_category", "unknown")
        adj_cat_counts[cat] = adj_cat_counts.get(cat, 0) + 1
    
    print(f"\nAdjusted category distribution:")
    for cat, count in sorted(adj_cat_counts.items()):
        print(f"  {cat}: {count}")
    
    if args.verbose:
        print("\nSample entries:")
        for gid in ["Dir 1.1", "Rule 22.8", "Rule 22.13", "Rule 21.3"]:
            if gid in output["guidelines"]:
                print(f"\n{gid}:")
                for k, v in output["guidelines"][gid].items():
                    print(f"  {k}: {v}")
    
    if args.dry_run:
        print(f"\nDry run - would write to: {output_path}")
        print(json.dumps(output, indent=2)[:2000] + "\n...")
    else:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to: {output_path}")
    
    return 0


if __name__ == "__main__":
    exit(main())
