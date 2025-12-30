#!/usr/bin/env python3
"""
Normalize FLS mapping JSON files to consistent schema.

This script:
1. Renames inconsistent top-level fields
2. Normalizes line numbers to arrays
3. Restructures sections using FLS semantic names
4. Merges orphan fields into appropriate sections
5. Marks missing required fields with "MUST_BE_FILLED"
"""

import json
import re
import sys
from pathlib import Path
from datetime import date
from typing import Any, Dict, List, Optional, Union

# Load FLS section mapping
SCRIPT_DIR = Path(__file__).parent
FLS_MAPPING_PATH = SCRIPT_DIR / "fls_section_mapping.json"

def load_fls_mapping() -> Dict:
    """Load the FLS section mapping file."""
    with open(FLS_MAPPING_PATH) as f:
        return json.load(f)

FLS_MAPPING = load_fls_mapping()


def normalize_line_number(value: Any) -> List[int]:
    """
    Convert various line number formats to array of integers.
    
    Examples:
        42 -> [42]
        "117" -> [117]
        "117-120" -> [117, 118, 119, 120]
        "various" -> []
        [42, 43] -> [42, 43]
    """
    if value is None:
        return []
    
    if isinstance(value, list):
        return [int(v) for v in value if str(v).isdigit()]
    
    if isinstance(value, int):
        return [value]
    
    if isinstance(value, str):
        value = value.strip()
        
        # Handle "various" or non-numeric
        if not any(c.isdigit() for c in value):
            return []
        
        # Handle range like "117-120"
        if '-' in value and not value.startswith('-'):
            parts = value.split('-')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start, end = int(parts[0]), int(parts[1])
                return list(range(start, end + 1))
        
        # Handle single number as string
        if value.isdigit():
            return [int(value)]
        
        # Handle comma-separated
        if ',' in value:
            nums = []
            for part in value.split(','):
                part = part.strip()
                if part.isdigit():
                    nums.append(int(part))
            return nums
    
    return []


def normalize_sample(sample: Dict) -> Dict:
    """
    Normalize a code sample to consistent format.
    
    Transforms:
        - path -> file
        - lines -> line (as array)
        - line_fragment -> code
    """
    normalized = {}
    
    # Handle file path
    if 'file' in sample:
        normalized['file'] = sample['file']
    elif 'path' in sample:
        normalized['file'] = sample['path']
    else:
        normalized['file'] = "MUST_BE_FILLED"
    
    # Handle line numbers
    if 'line' in sample:
        normalized['line'] = normalize_line_number(sample['line'])
    elif 'lines' in sample:
        normalized['line'] = normalize_line_number(sample['lines'])
    else:
        normalized['line'] = []
    
    # Handle code snippet
    if 'code' in sample:
        normalized['code'] = sample['code']
    elif 'line_fragment' in sample:
        normalized['code'] = sample['line_fragment']
    
    # Preserve other fields
    for key in ['purpose', 'name', 'description', 'note', 'action', 'type', 'variable', 'variables']:
        if key in sample:
            normalized[key] = sample[key]
    
    return normalized


def normalize_samples_in_object(obj: Any) -> Any:
    """Recursively normalize all samples in an object."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == 'samples' and isinstance(value, list):
                result[key] = [normalize_sample(s) if isinstance(s, dict) else s for s in value]
            else:
                result[key] = normalize_samples_in_object(value)
        return result
    elif isinstance(obj, list):
        return [normalize_samples_in_object(item) for item in obj]
    else:
        return obj


def get_fls_section_info(chapter: int, section_key: str) -> Optional[Dict]:
    """Get FLS section info from the mapping."""
    chapter_data = FLS_MAPPING.get(str(chapter), {})
    sections = chapter_data.get('sections', {})
    return sections.get(section_key)


def get_chapter_fls_id(chapter: int) -> Optional[str]:
    """Get the FLS ID for a chapter."""
    chapter_data = FLS_MAPPING.get(str(chapter), {})
    return chapter_data.get('fls_id')


def extract_section_key_from_numbered(key: str) -> str:
    """
    Extract semantic section key from numbered format.
    
    Examples:
        "3.1_modules" -> "modules"
        "section_2_1_character_set" -> "character_set"
        "21.1:1-10" -> "abi"
    """
    # Handle "section_N_N_name" format
    match = re.match(r'section_\d+_\d+_(.+)', key)
    if match:
        return match.group(1)
    
    # Handle "N.N_name" format
    match = re.match(r'\d+\.\d+_(.+)', key)
    if match:
        return match.group(1)
    
    # Handle "N.N" format (just section number)
    match = re.match(r'(\d+)\.(\d+)', key)
    if match:
        return key  # Keep as-is for now
    
    return key


def normalize_chapter(data: Dict, chapter_num: int) -> Dict:
    """Normalize a single chapter's JSON data."""
    normalized = {}
    
    # === Required top-level fields ===
    
    # Chapter number
    if 'chapter' in data:
        normalized['chapter'] = data['chapter']
    elif 'fls_chapter' in data:
        # Extract number from "3. Items" format
        match = re.match(r'(\d+)', str(data['fls_chapter']))
        normalized['chapter'] = int(match.group(1)) if match else chapter_num
    else:
        normalized['chapter'] = chapter_num
    
    # Title
    if 'title' in data:
        normalized['title'] = data['title']
    elif 'chapter_title' in data:
        normalized['title'] = data['chapter_title']
    else:
        chapter_info = FLS_MAPPING.get(str(chapter_num), {})
        normalized['title'] = chapter_info.get('title', "MUST_BE_FILLED")
    
    # FLS URL
    if 'fls_url' in data:
        normalized['fls_url'] = data['fls_url']
    elif 'fls_reference' in data:
        normalized['fls_url'] = data['fls_reference']
    else:
        normalized['fls_url'] = "MUST_BE_FILLED"
    
    # FLS ID (chapter level)
    chapter_fls_id = get_chapter_fls_id(chapter_num)
    if chapter_fls_id:
        normalized['fls_id'] = chapter_fls_id
    
    # Repository
    normalized['repository'] = "eclipse-iceoryx/iceoryx2"
    
    # Version
    normalized['version'] = data.get('version', "MUST_BE_FILLED")
    
    # Analysis date
    if 'analysis_date' in data:
        # Normalize date format
        date_str = data['analysis_date']
        if len(date_str) == 7:  # "2024-12" format
            normalized['analysis_date'] = f"{date_str}-30"
        else:
            normalized['analysis_date'] = date_str
    else:
        normalized['analysis_date'] = str(date.today())
    
    # Version changes
    if 'version_changes' in data:
        vc = data['version_changes']
        normalized['version_changes'] = {
            'from_version': vc.get('from_version', "MUST_BE_FILLED"),
            'to_version': vc.get('to_version', data.get('version', "MUST_BE_FILLED")),
            'summary': vc.get('summary', "MUST_BE_FILLED"),
            'key_changes': vc.get('key_changes', vc.get('notable_changes', []))
        }
    else:
        normalized['version_changes'] = {
            'from_version': "MUST_BE_FILLED",
            'to_version': data.get('version', "MUST_BE_FILLED"),
            'summary': "MUST_BE_FILLED",
            'key_changes': []
        }
    
    # Summary
    if 'summary' in data:
        normalized['summary'] = data['summary']
    elif 'overview' in data and isinstance(data['overview'], dict):
        normalized['summary'] = data['overview'].get('description', "MUST_BE_FILLED")
    else:
        normalized['summary'] = "MUST_BE_FILLED"
    
    # === Statistics ===
    normalized['statistics'] = {}
    
    # Collect from existing statistics
    if 'statistics' in data:
        normalized['statistics'].update(data['statistics'])
    
    # Merge orphan count fields
    count_fields = [
        'expression_counts', 'statement_counts', 'value_counts', 
        'literal_counts', 'pattern_counts'
    ]
    for field in count_fields:
        if field in data and isinstance(data[field], dict):
            normalized['statistics'].update(data[field])
    
    # === Sections ===
    normalized['sections'] = {}
    
    # Get FLS section info for this chapter
    chapter_fls_info = FLS_MAPPING.get(str(chapter_num), {})
    fls_sections = chapter_fls_info.get('sections', {})
    
    # Process existing sections
    if 'sections' in data and isinstance(data['sections'], dict):
        for key, value in data['sections'].items():
            if isinstance(value, str):
                # Simple string value (like "21.1": "ABI")
                semantic_key = extract_section_key_from_numbered(key)
                fls_info = fls_sections.get(semantic_key, {})
                normalized['sections'][semantic_key] = {
                    'fls_section': fls_info.get('fls_section', key),
                    'fls_ids': [fls_info['fls_id']] if fls_info.get('fls_id') else [],
                    'description': value,
                    'status': "MUST_BE_FILLED"
                }
            elif isinstance(value, dict):
                semantic_key = extract_section_key_from_numbered(key)
                fls_info = fls_sections.get(semantic_key, {})
                section = normalize_section(value, fls_info)
                normalized['sections'][semantic_key] = section
    
    # Process flat section_X_Y_name fields (like chapter 02)
    flat_section_keys = [k for k in data.keys() if k.startswith('section_')]
    for key in flat_section_keys:
        semantic_key = extract_section_key_from_numbered(key)
        fls_info = fls_sections.get(semantic_key, {})
        value = data[key]
        if isinstance(value, dict):
            section = normalize_section(value, fls_info)
            normalized['sections'][semantic_key] = section
    
    # Process top-level fields that should be sections
    section_like_fields = identify_section_like_fields(data, chapter_num)
    for field_name, target_section in section_like_fields.items():
        if field_name in data:
            field_value = data[field_name]
            if target_section not in normalized['sections']:
                fls_info = fls_sections.get(target_section, {})
                normalized['sections'][target_section] = {
                    'fls_section': fls_info.get('fls_section', "MUST_BE_FILLED"),
                    'fls_ids': [fls_info['fls_id']] if fls_info.get('fls_id') else [],
                    'description': fls_info.get('title', "MUST_BE_FILLED"),
                    'status': "MUST_BE_FILLED",
                    'findings': {},
                    'samples': []
                }
            
            # Merge the field value into the section
            section = normalized['sections'][target_section]
            if isinstance(field_value, dict):
                if 'findings' not in section:
                    section['findings'] = {}
                # Move samples out of findings into section samples
                if 'samples' in field_value:
                    if 'samples' not in section:
                        section['samples'] = []
                    section['samples'].extend(field_value.pop('samples'))
                section['findings'][field_name] = field_value
            elif isinstance(field_value, list):
                if 'samples' not in section:
                    section['samples'] = []
                # Check if it's a list of samples
                if field_value and isinstance(field_value[0], dict) and ('file' in field_value[0] or 'path' in field_value[0]):
                    section['samples'].extend(field_value)
                else:
                    section['findings'][field_name] = field_value
    
    # === Design Patterns ===
    if 'design_patterns' in data:
        normalized['design_patterns'] = normalize_samples_in_object(data['design_patterns'])
    
    # === Safety Critical Summary ===
    if 'safety_critical_summary' in data:
        normalized['safety_critical_summary'] = data['safety_critical_summary']
    else:
        # Check for orphan safety fields
        safety_fields = ['patterns_not_used', 'expressions_not_used', 'items_not_used', 'safety_patterns']
        has_safety = any(f in data for f in safety_fields)
        if has_safety:
            normalized['safety_critical_summary'] = {}
            for field in safety_fields:
                if field in data:
                    if 'not_used' in field:
                        if 'items_not_used' not in normalized['safety_critical_summary']:
                            normalized['safety_critical_summary']['items_not_used'] = {}
                        normalized['safety_critical_summary']['items_not_used'][field] = data[field]
                    else:
                        if 'positive_patterns' not in normalized['safety_critical_summary']:
                            normalized['safety_critical_summary']['positive_patterns'] = {}
                        normalized['safety_critical_summary']['positive_patterns'][field] = data[field]
    
    # === Cross Chapter References ===
    if 'cross_chapter_references' in data:
        normalized['cross_chapter_references'] = data['cross_chapter_references']
    
    # Normalize all samples recursively
    normalized = normalize_samples_in_object(normalized)
    
    return normalized


def normalize_section(value: Dict, fls_info: Dict) -> Dict:
    """Normalize a section object."""
    section = {}
    
    # FLS section number
    if 'fls_section' in value:
        section['fls_section'] = value['fls_section']
    elif fls_info.get('fls_section'):
        section['fls_section'] = fls_info['fls_section']
    else:
        section['fls_section'] = "MUST_BE_FILLED"
    
    # FLS paragraphs
    if 'fls_paragraphs' in value:
        section['fls_paragraphs'] = value['fls_paragraphs']
    
    # FLS IDs
    if 'fls_ids' in value:
        section['fls_ids'] = value['fls_ids']
    elif fls_info.get('fls_id'):
        section['fls_ids'] = [fls_info['fls_id']]
    
    # Description
    if 'description' in value:
        section['description'] = value['description']
    elif fls_info.get('title'):
        section['description'] = fls_info['title']
    else:
        section['description'] = "MUST_BE_FILLED"
    
    # Status
    if 'status' in value:
        section['status'] = value['status']
    
    # Findings - collect non-standard fields
    findings = {}
    standard_keys = {'fls_section', 'fls_paragraphs', 'fls_ids', 'description', 
                     'status', 'findings', 'samples', 'safety_notes', 'subsections',
                     'syntax', 'rules'}
    for key, val in value.items():
        if key not in standard_keys:
            findings[key] = val
    
    if 'findings' in value:
        findings.update(value['findings'])
    
    if findings:
        section['findings'] = findings
    
    # Samples
    if 'samples' in value:
        section['samples'] = value['samples']
    
    # Safety notes
    if 'safety_notes' in value:
        section['safety_notes'] = value['safety_notes']
    
    # Subsections
    if 'subsections' in value:
        section['subsections'] = {}
        for sub_key, sub_value in value['subsections'].items():
            if isinstance(sub_value, dict):
                section['subsections'][sub_key] = normalize_section(sub_value, {})
    
    return section


def identify_section_like_fields(data: Dict, chapter_num: int) -> Dict[str, str]:
    """
    Identify fields that should be moved into sections.
    Returns a mapping of field_name -> target_section_key.
    """
    mappings = {}
    
    # Chapter-specific mappings
    if chapter_num == 15:  # Ownership
        mappings.update({
            'ownership': 'ownership',
            'initialization': 'initialization',
            'references': 'references',
            'borrowing': 'borrowing',
            'passing_conventions': 'passing_conventions',
            'destruction': 'destruction',
            'destructors': 'destructors',
            'drop_scopes': 'drop_scopes',
            'drop_order': 'drop_order',
            'raii_guards': 'destructors',
            'manually_drop_usage': 'destructors',
            'mem_forget_usage': 'destruction',
        })
    
    elif chapter_num == 17:  # Concurrency
        mappings.update({
            'send_and_sync': 'send_and_sync',
            'atomics': 'atomics',
            'asynchronous_computation': 'asynchronous_computation',
            'spinlock': 'atomics',
            'lock_free_data_structures': 'atomics',
            'service_threading_models': 'send_and_sync',
            'synchronization_primitives': 'atomics',
        })
    
    elif chapter_num == 19:  # Unsafety
        mappings.update({
            'union_types': 'unsafe_operations',
            'unsafe_impl_categories': 'unsafe_operations',
            'static_mut_usage': 'unsafe_operations',
            'unsafe_fn_purposes': 'unsafe_operations',
            'unsafe_operation_patterns': 'unsafe_operations',
            'unsafe_trait': 'unsafe_operations',
            'safety_documentation': 'unsafe_operations',
            'testing_unsafe': 'unsafe_operations',
        })
    
    elif chapter_num == 20:  # Macros
        mappings.update({
            'declarative_macros': 'declarative_macros',
            'procedural_macros': 'procedural_macros',
            'macro_invocation': 'macro_invocation',
            'metavariables': 'declarative_macros',
            'repetition': 'declarative_macros',
            'hygiene': 'hygiene',
        })
    
    elif chapter_num == 21:  # FFI
        mappings.update({
            'abi_usage': 'abi',
            'ffi_c_crate': 'external_functions',
            'ffi_macros_crate': 'external_functions',
            'platform_abstraction_layer': 'external_blocks',
            'python_bindings': 'external_functions',
            'repr_c_types': 'abi',
            'union_types': 'abi',
            'c_api_error_handling': 'external_functions',
            'no_mangle_functions': 'external_functions',
        })
    
    elif chapter_num == 22:  # Inline Assembly
        mappings.update({
            'global_asm_usage': 'macros_asm_globalasm_and_nakedasm',
            'alternatives_used': 'macros_asm_globalasm_and_nakedasm',
            'fence_samples': 'macros_asm_globalasm_and_nakedasm',
            'bare_metal_example': 'macros_asm_globalasm_and_nakedasm',
            'design_decision': 'macros_asm_globalasm_and_nakedasm',
            'why_no_inline_assembly': 'macros_asm_globalasm_and_nakedasm',
        })
    
    elif chapter_num == 18:  # Program Structure
        mappings.update({
            'source_files': 'source_files',
            'modules': 'modules',
            'crates': 'crates',
            'crate_imports': 'crate_imports',
            'compilation_roots': 'compilation_roots',
            'conditional_compilation': 'conditional_compilation',
            'program_entry_point': 'program_entry_point',
            'prelude_module': 'modules',
        })
    
    return mappings


def normalize_file(input_path: Path, output_path: Path) -> Dict:
    """Normalize a single JSON file."""
    # Extract chapter number from filename
    match = re.search(r'chapter(\d+)', input_path.name)
    chapter_num = int(match.group(1)) if match else 0
    
    with open(input_path) as f:
        data = json.load(f)
    
    normalized = normalize_chapter(data, chapter_num)
    
    with open(output_path, 'w') as f:
        json.dump(normalized, f, indent=2)
    
    return normalized


def main():
    """Main entry point."""
    mapping_dir = Path("iceoryx2-fls-mapping")
    
    # Find all JSON files (excluding schema and backup)
    json_files = sorted(mapping_dir.glob("fls_chapter*.json"))
    
    print(f"Normalizing {len(json_files)} FLS mapping files...")
    
    for json_file in json_files:
        print(f"  Processing {json_file.name}...")
        try:
            normalize_file(json_file, json_file)
            print(f"    OK")
        except Exception as e:
            print(f"    ERROR: {e}")
            raise
    
    print("\nNormalization complete!")


if __name__ == "__main__":
    main()
