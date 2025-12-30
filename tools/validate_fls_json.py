#!/usr/bin/env python3
"""
Validate FLS mapping JSON files against schema.

Reports:
- Schema violations
- MUST_BE_FILLED markers
- Sample file path validity (if iceoryx2 repo available)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    print("Warning: jsonschema not installed. Schema validation will be skipped.")
    print("Install with: pip install jsonschema")


SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
MAPPING_DIR = ROOT_DIR / "iceoryx2-fls-mapping"
SCHEMA_PATH = MAPPING_DIR / "schema.json"
ICEORYX2_CACHE = ROOT_DIR / "cache" / "repos" / "iceoryx2"


def load_schema() -> Dict:
    """Load the JSON schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def find_must_be_filled(obj: Any, path: str = "") -> List[str]:
    """
    Recursively find all MUST_BE_FILLED markers.
    
    Returns list of JSON paths where markers are found.
    """
    results = []
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            if value == "MUST_BE_FILLED":
                results.append(new_path)
            else:
                results.extend(find_must_be_filled(value, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            results.extend(find_must_be_filled(item, new_path))
    elif obj == "MUST_BE_FILLED":
        results.append(path)
    
    return results


def find_sample_paths(obj: Any, path: str = "") -> List[Tuple[str, str, List[int]]]:
    """
    Recursively find all code sample file paths.
    
    Returns list of (json_path, file_path, line_numbers).
    """
    results = []
    
    if isinstance(obj, dict):
        if 'file' in obj and 'line' in obj:
            # This is a sample
            file_path = obj.get('file', '')
            line_nums = obj.get('line', [])
            if file_path and file_path != "MUST_BE_FILLED":
                results.append((path, file_path, line_nums))
        else:
            for key, value in obj.items():
                new_path = f"{path}.{key}" if path else key
                results.extend(find_sample_paths(value, new_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            new_path = f"{path}[{i}]"
            results.extend(find_sample_paths(item, new_path))
    
    return results


def validate_sample_paths(samples: List[Tuple[str, str, List[int]]], version: str) -> List[str]:
    """
    Validate that sample file paths exist in the iceoryx2 repo.
    
    Returns list of error messages.
    """
    errors = []
    repo_path = ICEORYX2_CACHE / f"v{version}"
    
    if not repo_path.exists():
        return [f"iceoryx2 repo not found at {repo_path}. Skipping path validation."]
    
    for json_path, file_path, line_nums in samples:
        full_path = repo_path / file_path
        if not full_path.exists():
            errors.append(f"{json_path}: File not found: {file_path}")
        elif line_nums:
            # Handle line_nums that might be int instead of list
            if isinstance(line_nums, int):
                line_nums = [line_nums]
            elif not isinstance(line_nums, list):
                continue  # Skip invalid line_nums
            
            # Optionally verify line numbers exist
            try:
                with open(full_path) as f:
                    lines = f.readlines()
                    max_line = len(lines)
                    for line_num in line_nums:
                        if line_num > max_line:
                            errors.append(f"{json_path}: Line {line_num} exceeds file length ({max_line}): {file_path}")
            except Exception as e:
                errors.append(f"{json_path}: Error reading {file_path}: {e}")
    
    return errors


def validate_file(file_path: Path, schema: Dict) -> Dict:
    """
    Validate a single JSON file.
    
    Returns dict with:
        - valid: bool
        - schema_errors: list of schema errors
        - must_be_filled: list of MUST_BE_FILLED locations
        - path_errors: list of invalid sample paths
    """
    result = {
        'file': file_path.name,
        'valid': True,
        'schema_errors': [],
        'must_be_filled': [],
        'path_errors': []
    }
    
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result['valid'] = False
        result['schema_errors'].append(f"Invalid JSON: {e}")
        return result
    
    # Schema validation
    if HAS_JSONSCHEMA:
        import jsonschema as js
        try:
            js.validate(data, schema)
        except js.ValidationError as e:
            result['valid'] = False
            result['schema_errors'].append(f"{e.json_path}: {e.message}")
        except js.SchemaError as e:
            result['valid'] = False
            result['schema_errors'].append(f"Schema error: {e.message}")
    
    # Find MUST_BE_FILLED markers
    result['must_be_filled'] = find_must_be_filled(data)
    
    # Validate sample paths
    samples = find_sample_paths(data)
    version = data.get('version', '0.8.0')
    result['path_errors'] = validate_sample_paths(samples, version)
    
    return result


def generate_report(results: List[Dict]) -> str:
    """Generate a validation report."""
    lines = []
    lines.append("=" * 60)
    lines.append("FLS MAPPING VALIDATION REPORT")
    lines.append("=" * 60)
    lines.append("")
    
    total_files = len(results)
    valid_files = sum(1 for r in results if r['valid'])
    total_must_fill = sum(len(r['must_be_filled']) for r in results)
    total_path_errors = sum(len(r['path_errors']) for r in results)
    
    lines.append(f"Files validated: {total_files}")
    lines.append(f"Schema valid: {valid_files}/{total_files}")
    lines.append(f"MUST_BE_FILLED markers: {total_must_fill}")
    lines.append(f"Path errors: {total_path_errors}")
    lines.append("")
    
    # Per-file details
    for result in results:
        lines.append("-" * 60)
        lines.append(f"FILE: {result['file']}")
        lines.append("-" * 60)
        
        if result['schema_errors']:
            lines.append("  SCHEMA ERRORS:")
            for err in result['schema_errors']:
                lines.append(f"    - {err}")
        
        if result['must_be_filled']:
            lines.append(f"  MUST_BE_FILLED ({len(result['must_be_filled'])}):")
            for path in result['must_be_filled'][:10]:  # Limit to first 10
                lines.append(f"    - {path}")
            if len(result['must_be_filled']) > 10:
                lines.append(f"    ... and {len(result['must_be_filled']) - 10} more")
        
        if result['path_errors']:
            lines.append(f"  PATH ERRORS ({len(result['path_errors'])}):")
            for err in result['path_errors'][:5]:  # Limit to first 5
                lines.append(f"    - {err}")
            if len(result['path_errors']) > 5:
                lines.append(f"    ... and {len(result['path_errors']) - 5} more")
        
        if not result['schema_errors'] and not result['must_be_filled'] and not result['path_errors']:
            lines.append("  OK - No issues found")
        
        lines.append("")
    
    # Summary of all MUST_BE_FILLED
    lines.append("=" * 60)
    lines.append("MUST_BE_FILLED INVENTORY")
    lines.append("=" * 60)
    
    for result in results:
        if result['must_be_filled']:
            lines.append(f"\n{result['file']}:")
            for path in result['must_be_filled']:
                lines.append(f"  - {path}")
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    # Load schema
    if SCHEMA_PATH.exists():
        schema = load_schema()
    else:
        print(f"Warning: Schema not found at {SCHEMA_PATH}")
        schema = {}
    
    # Find all JSON files
    json_files = sorted(MAPPING_DIR.glob("fls_chapter*.json"))
    
    if not json_files:
        print("No FLS mapping files found.")
        return 1
    
    print(f"Validating {len(json_files)} files...")
    
    results = []
    for json_file in json_files:
        print(f"  Checking {json_file.name}...")
        result = validate_file(json_file, schema)
        results.append(result)
    
    # Generate report
    report = generate_report(results)
    print("\n" + report)
    
    # Write report to file
    report_path = ROOT_DIR / "validation_report.txt"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")
    
    # Return exit code
    all_valid = all(r['valid'] for r in results)
    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
