#!/usr/bin/env -S uv run python
"""
Scrape CERT C and CERT C++ rules from the SEI CERT Wiki.

This script extracts rule and recommendation IDs and titles from the
SEI CERT Secure Coding Standards wiki pages.

Usage:
    uv run python tools/scrape_cert_rules.py

Output:
    coding-standards-fls-mapping/standards/cert_c.json
    coding-standards-fls-mapping/standards/cert_cpp.json
"""

import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = ROOT_DIR / "coding-standards-fls-mapping" / "standards"

# Base URLs
CERT_BASE = "https://wiki.sei.cmu.edu"
CERT_C_MAIN = f"{CERT_BASE}/confluence/display/c/SEI+CERT+C+Coding+Standard"
CERT_CPP_MAIN = f"{CERT_BASE}/confluence/pages/viewpage.action?pageId=88046682"

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between requests


@dataclass
class Guideline:
    """A single rule or recommendation."""

    id: str
    title: str
    guideline_type: str  # "rule" or "recommendation"


@dataclass
class Category:
    """A category grouping related guidelines."""

    id: str
    name: str
    guidelines: list[Guideline]


def fetch_page(url: str) -> str:
    """Fetch a page with rate limiting."""
    time.sleep(REQUEST_DELAY)
    response = httpx.get(url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    return response.text


def parse_cert_c_main_page(html: str) -> list[tuple[str, str, str, str]]:
    """
    Parse the CERT C main page to get category URLs.

    Returns list of (category_id, category_name, url, type) tuples.
    """
    soup = BeautifulSoup(html, "html.parser")
    categories = []

    # Find all links to rule and recommendation categories
    # Pattern: "Rule XX. Category Name (ABC)" or "Rec. XX. Category Name (ABC)"
    for link in soup.find_all("a"):
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Match rule categories
        rule_match = re.match(r"Rule\s+(\d+)\.\s+(.+?)\s+\((\w+)\)", text)
        if rule_match and "/confluence/" in href:
            name = rule_match.group(2)
            abbrev = rule_match.group(3)
            full_url = f"{CERT_BASE}{href}" if href.startswith("/") else href
            categories.append((abbrev, f"{name} ({abbrev})", full_url, "rule"))

        # Match recommendation categories
        rec_match = re.match(r"Rec\.\s+(\d+)\.\s+(.+?)\s+\((\w+)\)", text)
        if rec_match and "/confluence/" in href:
            name = rec_match.group(2)
            abbrev = rec_match.group(3)
            full_url = f"{CERT_BASE}{href}" if href.startswith("/") else href
            categories.append((abbrev, f"{name} ({abbrev})", full_url, "recommendation"))

    return categories


def parse_cert_cpp_main_page(html: str) -> list[tuple[str, str, str, str]]:
    """
    Parse the CERT C++ main page to get category URLs.

    Returns list of (category_id, category_name, url, type) tuples.
    """
    soup = BeautifulSoup(html, "html.parser")
    categories = []

    for link in soup.find_all("a"):
        href = link.get("href", "")
        text = link.get_text(strip=True)

        # Match rule categories - C++ uses format like "Rule 01. Declarations and Initialization (DCL)"
        rule_match = re.match(r"Rule\s+(\d+)\.\s+(.+?)\s+\((\w+)\)", text)
        if rule_match and "/confluence/" in href:
            name = rule_match.group(2)
            abbrev = rule_match.group(3)
            full_url = f"{CERT_BASE}{href}" if href.startswith("/") else href
            categories.append((abbrev, f"{name} ({abbrev})", full_url, "rule"))

    return categories


def parse_category_page(html: str, category_abbrev: str, guideline_type: str) -> list[Guideline]:
    """
    Parse a category page to extract individual guidelines.

    Returns list of Guideline objects.
    """
    soup = BeautifulSoup(html, "html.parser")
    guidelines = []

    # Pattern for CERT rules: ABC00-C or ABC00-CPP
    # The -C suffix indicates C rules, -CPP indicates C++ rules
    pattern = re.compile(rf"({category_abbrev}\d+)-(C|CPP)\.\s*(.+)")

    for link in soup.find_all("a"):
        text = link.get_text(strip=True)
        match = pattern.match(text)
        if match:
            rule_id = f"{match.group(1)}-{match.group(2)}"
            title = match.group(3).strip()

            # Determine if this is a rule or recommendation based on number
            # Rules are typically 30+ (e.g., MEM30-C), recommendations are 00-29
            try:
                num = int(re.search(r"\d+", match.group(1)).group())
                actual_type = "rule" if num >= 30 else "recommendation"
            except (AttributeError, ValueError):
                actual_type = guideline_type

            guidelines.append(Guideline(id=rule_id, title=title, guideline_type=actual_type))

    return guidelines


def scrape_cert_c() -> tuple[list[Category], dict]:
    """Scrape all CERT C rules and recommendations."""
    print("Fetching CERT C main page...")
    main_html = fetch_page(CERT_C_MAIN)

    categories_info = parse_cert_c_main_page(main_html)
    print(f"Found {len(categories_info)} categories")

    categories = []
    seen_guidelines = set()

    for abbrev, name, url, cat_type in categories_info:
        print(f"  Fetching {abbrev}...")
        try:
            html = fetch_page(url)
            guidelines = parse_category_page(html, abbrev, cat_type)

            # Deduplicate
            unique_guidelines = []
            for g in guidelines:
                if g.id not in seen_guidelines:
                    seen_guidelines.add(g.id)
                    unique_guidelines.append(g)

            if unique_guidelines:
                categories.append(
                    Category(id=abbrev, name=name, guidelines=unique_guidelines)
                )
                print(f"    Found {len(unique_guidelines)} guidelines")
        except Exception as e:
            print(f"    Error: {e}")

    # Compute statistics
    total_rules = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "rule"
    )
    total_recs = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "recommendation"
    )
    stats = {
        "total_guidelines": total_rules + total_recs,
        "rules": total_rules,
        "directives": 0,
        "recommendations": total_recs,
        "categories": len(categories),
    }

    return categories, stats


def scrape_cert_cpp() -> tuple[list[Category], dict]:
    """Scrape all CERT C++ rules."""
    print("Fetching CERT C++ main page...")
    main_html = fetch_page(CERT_CPP_MAIN)

    categories_info = parse_cert_cpp_main_page(main_html)
    print(f"Found {len(categories_info)} categories")

    categories = []
    seen_guidelines = set()

    for abbrev, name, url, cat_type in categories_info:
        print(f"  Fetching {abbrev}...")
        try:
            html = fetch_page(url)
            guidelines = parse_category_page(html, abbrev, cat_type)

            # Deduplicate
            unique_guidelines = []
            for g in guidelines:
                if g.id not in seen_guidelines:
                    seen_guidelines.add(g.id)
                    unique_guidelines.append(g)

            if unique_guidelines:
                categories.append(
                    Category(id=abbrev, name=name, guidelines=unique_guidelines)
                )
                print(f"    Found {len(unique_guidelines)} guidelines")
        except Exception as e:
            print(f"    Error: {e}")

    # Compute statistics
    total_rules = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "rule"
    )
    total_recs = sum(
        1 for c in categories for g in c.guidelines if g.guideline_type == "recommendation"
    )
    stats = {
        "total_guidelines": total_rules + total_recs,
        "rules": total_rules,
        "directives": 0,
        "recommendations": total_recs,
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
    """Scrape CERT rules and save to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Scrape CERT C
    print("=" * 60)
    print("Scraping CERT C Coding Standard")
    print("=" * 60)
    categories, stats = scrape_cert_c()

    output = {
        "standard": "CERT-C",
        "version": "2016 Edition (wiki current)",
        "extraction_date": date.today().isoformat(),
        "source": CERT_C_MAIN,
        "statistics": stats,
        "categories": categories_to_dict(categories),
    }

    output_path = OUTPUT_DIR / "cert_c.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nExtracted {stats['rules']} rules, {stats['recommendations']} recommendations")
    print(f"Saved to {output_path}")

    # Scrape CERT C++
    print("\n" + "=" * 60)
    print("Scraping CERT C++ Coding Standard")
    print("=" * 60)
    categories, stats = scrape_cert_cpp()

    output = {
        "standard": "CERT-C++",
        "version": "2016 Edition (wiki current)",
        "extraction_date": date.today().isoformat(),
        "source": CERT_CPP_MAIN,
        "statistics": stats,
        "categories": categories_to_dict(categories),
    }

    output_path = OUTPUT_DIR / "cert_cpp.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nExtracted {stats['rules']} rules, {stats['recommendations']} recommendations")
    print(f"Saved to {output_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
