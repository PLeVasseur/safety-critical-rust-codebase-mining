#!/usr/bin/env python3
"""
Generate the valid_fls_ids.json file from all canonical sources.

This tool extracts all valid FLS IDs from:
1. fls_section_mapping.json - Section-level IDs
2. synthetic_fls_ids.json - Fabricated/synthetic IDs
3. embeddings/fls/chapter_*.json - Paragraph-level IDs

The output is written to tools/data/valid_fls_ids.json and is used by
record-decision to validate FLS IDs at recording time.

This tool is automatically called by extract-fls-content, but can also
be run standalone if you need to regenerate the list without re-extracting
FLS content.

Usage:
    uv run generate-valid-fls-ids
"""

import sys

from fls_tools.shared import get_project_root
from fls_tools.shared.fls_ids import generate_valid_fls_ids, get_valid_fls_ids_path


def main() -> int:
    """Generate the valid FLS IDs file."""
    root = get_project_root()
    
    print("Generating valid FLS IDs list...")
    print()
    
    data = generate_valid_fls_ids(root)
    
    output_path = get_valid_fls_ids_path(root)
    
    print(f"Sources:")
    for source in data["sources"]:
        print(f"  - {source}")
    print()
    
    print(f"Counts:")
    print(f"  Section mapping:  {data['counts']['section_mapping']:,}")
    print(f"  Synthetic:        {data['counts']['synthetic']:,}")
    print(f"  Embeddings:       {data['counts']['embeddings']:,}")
    print(f"  Total unique:     {data['counts']['total_unique']:,}")
    print()
    
    print(f"Output: {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
