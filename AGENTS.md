# FLS Mapping Update Agent Guide

This document describes the methodology for updating the Ferrocene Language Specification (FLS) mapping JSON files when a new version of iceoryx2 is released.

## Overview

The FLS mapping files in `iceoryx2-fls-mapping/` document how iceoryx2 uses various Rust language constructs as defined by the Ferrocene Language Specification. Each JSON file corresponds to a chapter of the FLS and contains:

- Statistics on language construct usage
- Code samples with file paths and line numbers
- Legality rule compliance documentation
- Safety-critical pattern analysis

## Current Status

**All chapters updated to v0.8.0** - Completed 2025-12-30

- 21 chapter JSON files (chapters 2-22)
- 0 MUST_BE_FILLED markers remaining
- All files pass schema validation
- Chapter 1 (General) intentionally excluded (metadata, not language constructs)

Next update required when iceoryx2 v0.9.0 or later is released.

### Recent Updates (2025-12-30)

1. **Fixed Chapter 13 JSON structure** - Subsections for `builtin_attributes` had escaped to become siblings instead of children. Restructured to properly nest all 13.2.x sections inside `builtin_attributes.subsections`.

2. **Enhanced validation script** - Added FLS coverage checking, FLS ID validation, and section hierarchy validation. See [Validation](#validation) section below.

3. **Dependency management cleanup** - `jsonschema` is now a required dependency in `pyproject.toml`, managed via `uv`.

## Repository Structure

```
eclipse-iceoryx2-actionanable-safety-certification/
├── iceoryx2-fls-mapping/           # FLS chapter mapping JSON files
│   ├── schema.json                 # JSON Schema for all mapping files
│   ├── backup/                     # Backup of original files before normalization
│   ├── fls_chapter02_lexical_elements.json
│   ├── fls_chapter03_items.json
│   ├── fls_chapter04_types_and_traits.json
│   ├── fls_chapter05_patterns.json
│   ├── fls_chapter06_expressions.json
│   ├── fls_chapter07_values.json
│   ├── fls_chapter08_statements.json
│   ├── fls_chapter09_functions.json
│   ├── fls_chapter10_associated_items.json
│   ├── fls_chapter11_implementations.json
│   ├── fls_chapter12_generics.json
│   ├── fls_chapter13_attributes.json
│   ├── fls_chapter14_entities_resolution.json
│   ├── fls_chapter15_ownership_destruction.json
│   ├── fls_chapter16_exceptions_errors.json
│   ├── fls_chapter17_concurrency.json
│   ├── fls_chapter18_program_structure.json
│   ├── fls_chapter19_unsafety.json
│   ├── fls_chapter20_macros.json
│   ├── fls_chapter21_ffi.json
│   └── fls_chapter22_inline_assembly.json
├── cache/repos/iceoryx2/           # Cached iceoryx2 versions
│   ├── v0.7.0/
│   └── v0.8.0/
├── cache/repos/fls/                # FLS specification source
└── tools/                          # Helper scripts
    ├── clone_iceoryx2.py           # Script to clone specific versions
    ├── fls_section_mapping.json    # FLS section names extracted from .rst files
    ├── normalize_fls_json.py       # Normalize JSON files to consistent schema
    └── validate_fls_json.py        # Validate JSON files against schema
```

## JSON Schema

All FLS mapping JSON files conform to the schema defined in `iceoryx2-fls-mapping/schema.json`. The schema enforces consistent structure across all chapters.

### Required Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `chapter` | integer | FLS chapter number (1-25) |
| `title` | string | Chapter title from FLS |
| `fls_url` | string (URI) | URL to FLS chapter specification |
| `fls_id` | string | FLS chapter identifier (e.g., `fls_jep7p27kaqlp`) |
| `repository` | string | Always `"eclipse-iceoryx/iceoryx2"` |
| `version` | string | Semver version analyzed (e.g., `"0.8.0"`) |
| `analysis_date` | string | ISO 8601 date (YYYY-MM-DD) |
| `version_changes` | object | Changes from previous version |
| `summary` | string | Executive summary of findings |
| `statistics` | object | Quantitative counts of language constructs |
| `sections` | object | FLS section mappings keyed by semantic name |

### Section Structure

Each section uses semantic keys (not numbered keys) and includes:

```json
{
  "sections": {
    "ownership": {
      "fls_section": "15.1",
      "fls_paragraphs": ["15.1:1", "15.1:2", "15.1:3"],
      "fls_ids": ["fls_svkx6szhr472"],
      "description": "Ownership is a property of values...",
      "status": "demonstrated",
      "findings": { ... },
      "samples": [ ... ],
      "safety_notes": [ ... ],
      "subsections": { ... }
    }
  }
}
```

### Code Sample Format

All code samples use a consistent format with line numbers as arrays:

```json
{
  "file": "iceoryx2-bb/posix/src/mutex.rs",
  "line": [186, 187, 188],
  "code": "pub struct MutexGuard<'a, T> { ... }",
  "purpose": "RAII guard for mutex unlock"
}
```

### MUST_BE_FILLED Markers

Fields requiring data that couldn't be automatically determined are marked with `"MUST_BE_FILLED"`. Run the validation script to find these:

```bash
python tools/validate_fls_json.py
```

### Validation

To validate all JSON files:

```bash
# Run with uv (recommended - handles dependencies automatically)
uv run python tools/validate_fls_json.py

# Limit coverage check depth (e.g., top-level sections only)
uv run python tools/validate_fls_json.py --depth=1

# Validate a specific file
uv run python tools/validate_fls_json.py --file=fls_chapter13_attributes.json
```

The validation script performs comprehensive checks:

| Check | Description |
|-------|-------------|
| **Schema validation** | Validates JSON structure against `schema.json` |
| **MUST_BE_FILLED detection** | Finds placeholder markers needing completion |
| **Sample path validation** | Verifies code sample paths exist in iceoryx2 repo |
| **FLS coverage check** | Ensures all FLS sections from `fls_section_mapping.json` are documented |
| **FLS ID validation** | Verifies `fls_ids` match canonical FLS identifiers |
| **Section hierarchy validation** | Checks `fls_section` numbering is well-formed (X.Y.Z pattern) |

#### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks pass |
| 1 | Schema validation failed (invalid JSON structure) |
| 2 | FLS coverage check failed (missing required sections) |
| 3 | FLS ID validation failed (invalid IDs found) |
| 4 | Multiple failures (combination of above) |

#### FLS Section Mapping

The file `tools/fls_section_mapping.json` contains the canonical FLS section hierarchy extracted from the FLS RST source files. It includes:
- All section numbers (e.g., 13.1, 13.2, 13.2.1)
- Section titles
- FLS IDs (where available - some sections have `null` if no anchor in source)

Sections marked with `fls_extracted_from_syntax_block` were programmatically extracted from syntax blocks in the FLS source and don't have native FLS ID anchors.

#### FLS Section Number Encoding

For FLS content that doesn't have traditional section headings, we use a special encoding with negative numbers:

| Pattern | Meaning | Example |
|---------|---------|---------|
| `X.Y` | Standard sections | `8.1` (Let Statements) |
| `X.0.Y` | Syntax block productions | (extracted from `.. syntax::` blocks) |
| `X.-1.Y` | Top-level unsorted items | (items before first heading) |
| `X.-2.Y` | Legality rules | `8.-2.1` (Item Statement legality rule) |
| `X.-3.Y` | Dynamic semantics | `8.-3.1` (Empty Statement Execution) |

This encoding allows us to reference and track FLS content that exists outside the traditional section hierarchy, particularly legality rules and dynamic semantics which are critical for safety certification.

### Normalization

To normalize JSON files to the schema (after manual edits):

```bash
python tools/normalize_fls_json.py
```

This script:
- Renames inconsistent fields (`fls_chapter` → `chapter`, etc.)
- Normalizes line numbers to arrays
- Restructures sections using FLS semantic names
- Merges orphan fields into appropriate sections

## Update Workflow

### 1. Prerequisites

Ensure both iceoryx2 versions are available:
- Old version: `cache/repos/iceoryx2/v{OLD_VERSION}/`
- New version: `cache/repos/iceoryx2/v{NEW_VERSION}/`

Use `tools/clone_iceoryx2.py` to clone specific versions if needed.

### 2. Review Changelog

Before updating, review the iceoryx2 changelog to understand major changes:
- `cache/repos/iceoryx2/v{NEW_VERSION}/doc/release-notes/iceoryx2-v{NEW_VERSION}.md`

Key things to look for:
- Directory structure changes (e.g., `iceoryx2-bb-posix-0.7.0/` → `iceoryx2-bb/posix/`)
- New language features used (e.g., unions, new traits)
- New crates added (e.g., `iceoryx2-ffi/c` for FFI)
- MSRV changes affecting available language features

### 3. Update Each Chapter

For each FLS chapter JSON file, perform these steps:

#### 3.1 Read Current File
```bash
# Read the existing JSON to understand its structure
cat iceoryx2-fls-mapping/fls_chapter{NN}_{name}.json
```

#### 3.2 Gather Statistics

Use `rg` (ripgrep) to count language constructs in the new version:

```bash
cd cache/repos/iceoryx2/v{NEW_VERSION}

# Count pattern occurrences across all Rust files
rg -c 'PATTERN' --type rust 2>/dev/null | awk -F: '{sum+=$2} END {print sum}'

# Find sample code with line numbers
rg -n 'PATTERN' --type rust | head -5
```

#### 3.3 Common Patterns to Count

**Chapter 6 - Expressions:**
```bash
rg -c '\bmatch\b' --type rust           # match expressions
rg -c '\bif let\b' --type rust          # if let
rg -c '\bwhile let\b' --type rust       # while let
rg -c '\bunsafe\s*\{' --type rust       # unsafe blocks
rg -c '\bloop\s*\{' --type rust         # loop expressions
rg -c '\bfor\b.*\bin\b' --type rust     # for loops
rg -c '\?' --type rust                  # error propagation
```

**Chapter 7 - Values:**
```bash
rg -c '\bconst\s+[A-Z]' --type rust     # const declarations
rg -c '\bstatic\s+mut\b' --type rust    # static mut
rg -c '\blet\s+[a-z_]' --type rust      # let bindings
rg -c '\blet\s+mut\b' --type rust       # let mut bindings
rg -c '\bMaybeUninit\b' --type rust     # MaybeUninit usage
rg -c '\bUnsafeCell\b' --type rust      # UnsafeCell usage
```

**Chapter 9 - Functions:**
```bash
rg -c '\bpub\s+fn\b' --type rust        # public functions
rg -c '\bunsafe\s+fn\b' --type rust     # unsafe functions
rg -c '\bconst\s+fn\b' --type rust      # const functions
rg -c '\bextern\s+"C"\s+fn\b' --type rust  # extern C functions
rg -c '#\[no_mangle\]' --type rust      # no_mangle attribute
```

**Chapter 15 - Ownership:**
```bash
rg -c 'impl\s+Drop\s+for' --type rust   # Drop implementations
rg -c 'derive.*Copy' --type rust        # Copy derives
rg -c 'ManuallyDrop' --type rust        # ManuallyDrop usage
rg -c 'PhantomData' --type rust         # PhantomData markers
rg -c 'mem::forget' --type rust         # mem::forget usage
```

**Chapter 17 - Concurrency:**
```bash
rg -c '\bAtomic' --type rust            # Atomic types
rg -c '\bOrdering::' --type rust        # Memory ordering
rg -c 'unsafe\s+impl\s+Send' --type rust # unsafe impl Send
rg -c 'unsafe\s+impl\s+Sync' --type rust # unsafe impl Sync
rg -c '\bSpinLock\b' --type rust        # SpinLock usage
```

**Chapter 19 - Unsafety:**
```bash
rg -c '\bunsafe\s*\{' --type rust       # unsafe blocks
rg -c '\bunsafe\s+fn\b' --type rust     # unsafe functions
rg -c '\bunsafe\s+impl\b' --type rust   # unsafe impl
rg -c '\bunsafe\s+trait\b' --type rust  # unsafe trait
rg -c '\bunion\b' --type rust           # union types
```

**Chapter 20 - Macros:**
```bash
rg -c 'macro_rules!' --type rust        # declarative macros
rg -c '#\[proc_macro' --type rust       # procedural macros
rg -c '#\[macro_export' --type rust     # exported macros
rg -c '\$crate::' --type rust           # $crate usage
```

**Chapter 21 - FFI:**
```bash
rg -c 'extern\s+"C"\s*\{' --type rust   # extern C blocks
rg -c '\bextern\s+"C"\s+fn\b' --type rust  # extern C functions
rg -c '#\[no_mangle\]' --type rust      # no_mangle
rg -c '#\[repr\(C\)\]' --type rust      # repr(C)
rg -c '\bunion\b' --type rust           # union types
```

**Chapter 22 - Inline Assembly:**
```bash
rg -c '\basm!\b' --type rust            # asm! macro
rg -c 'global_asm!' --type rust         # global_asm! macro
rg -c '\bfence\(' --type rust           # memory fences
rg -c 'compiler_fence\(' --type rust    # compiler fences
```

#### 3.4 Update JSON Structure

Each JSON file should include:

```json
{
  "chapter": N,
  "title": "Chapter Name",
  "fls_url": "https://...",
  "version": "0.8.0",
  "analysis_date": "YYYY-MM-DD",
  "version_changes": {
    "from_version": "0.7.0",
    "to_version": "0.8.0",
    "summary": "Brief description of major changes",
    "key_changes": [
      "Change 1 with percentage if applicable",
      "Change 2 with percentage if applicable"
    ]
  },
  "summary": "Updated summary reflecting new version",
  "statistics": { ... },
  // ... rest of chapter-specific content
}
```

#### 3.5 Update File Paths

Convert old paths to new structure:
- `iceoryx2-bb-posix-0.7.0/` → `iceoryx2-bb/posix/`
- `iceoryx2-bb-memory-0.7.0/` → `iceoryx2-bb/memory/`
- `iceoryx2-bb-log-0.7.0/` → `iceoryx2-log/log/` (logger was restructured)
- etc.

#### 3.6 Verify Sample Code

For each code sample, verify it still exists at the specified location:
```bash
rg -n 'CODE_SNIPPET' path/to/file.rs
```

Update line numbers as needed.

## Key Changes v0.7.0 → v0.8.0

### Directory Structure
| Old (v0.7.0) | New (v0.8.0) |
|--------------|--------------|
| `iceoryx2-bb-container-0.7.0/` | `iceoryx2-bb/container/` |
| `iceoryx2-bb-elementary-0.7.0/` | `iceoryx2-bb/elementary/` |
| `iceoryx2-bb-lock-free-0.7.0/` | `iceoryx2-bb/lock-free/` |
| `iceoryx2-bb-log-0.7.0/` | `iceoryx2-log/log/` + `iceoryx2-log/loggers/` |
| `iceoryx2-bb-memory-0.7.0/` | `iceoryx2-bb/memory/` |
| `iceoryx2-bb-posix-0.7.0/` | `iceoryx2-bb/posix/` |
| `iceoryx2-bb-system-types-0.7.0/` | `iceoryx2-bb/system-types/` |
| `iceoryx2-bb-testing-0.7.0/` | `iceoryx2-bb/testing/` |
| `iceoryx2-pal-posix-0.7.0/` | `iceoryx2-pal/posix/` |
| `iceoryx2-pal-concurrency-sync-0.7.0/` | `iceoryx2-pal/concurrency-sync/` |
| `iceoryx2-cal-0.7.0/` | `iceoryx2-cal/` |
| `iceoryx2-0.7.0/` | `iceoryx2/` |

### Major Feature Changes
1. **Union types now used**: 42 union definitions (was 0 in v0.7.0) - for FFI C bindings
2. **Logger restructured**: Split into `iceoryx2-log/log` and `iceoryx2-loggers`
3. **no_std support added**: Explicit `extern crate alloc/core` imports
4. **New container types**: `StaticVec<T, N>` and `StaticString<N>`
5. **MSRV increased to 1.83**
6. **Expanded FFI layer**: `iceoryx2-ffi/c` crate with 600+ extern C functions
7. **static mut increased**: 3 → 14 due to logger restructuring

### Key Statistics Comparison

| Metric | v0.7.0 | v0.8.0 | Change |
|--------|--------|--------|--------|
| unsafe blocks | 1,702 | 2,372 | +39% |
| unsafe fn | 1,302 | 1,763 | +35% |
| extern "C" fn | 17 | 630 | +3606% |
| #[no_mangle] | ~0 | 602 | new |
| union types | 0 | 42 | new |
| static mut | 3 | 14 | +367% |
| Total functions | 4,909 | 8,422 | +72% |
| impl blocks | 1,353 | 2,397 | +77% |
| match expressions | 712 | 1,663 | +134% |
| ManuallyDrop | 0 | 541 | new |

## Chapter Update Tracking

### v0.8.0 Update (Completed 2025-12-30)

- [x] Chapter 02 - Lexical Elements
- [x] Chapter 03 - Items
- [x] Chapter 04 - Types and Traits
- [x] Chapter 05 - Patterns
- [x] Chapter 06 - Expressions
- [x] Chapter 07 - Values
- [x] Chapter 08 - Statements
- [x] Chapter 09 - Functions
- [x] Chapter 10 - Associated Items
- [x] Chapter 11 - Implementations
- [x] Chapter 12 - Generics
- [x] Chapter 13 - Attributes
- [x] Chapter 14 - Entities Resolution
- [x] Chapter 15 - Ownership Destruction
- [x] Chapter 16 - Exceptions and Errors
- [x] Chapter 17 - Concurrency
- [x] Chapter 18 - Program Structure
- [x] Chapter 19 - Unsafety
- [x] Chapter 20 - Macros
- [x] Chapter 21 - FFI
- [x] Chapter 22 - Inline Assembly

### Key Changes by Chapter (v0.7.0 → v0.8.0)

| Chapter | Key Changes |
|---------|-------------|
| **21 - FFI** | MASSIVE: 630 extern C fn (+3606%), 602 #[no_mangle], 42 unions, new iceoryx2-ffi/c crate |
| **19 - Unsafety** | unsafe blocks +39%, unsafe fn +35%, 42 unions, 541 ManuallyDrop |
| **18 - Program Structure** | 37+ crates (+164%), 1071 source files (+96%), 23 no_std crates |
| **17 - Concurrency** | Atomic wrappers restructured, SpinLock added, Mutex +503% |
| **15 - Ownership** | ManuallyDrop 0→541, UnsafeCell +172%, FFI union handling |
| **20 - Macros** | 28 macros (+75%), 6 proc-macros (+200%), 3 proc-macro crates |
| **22 - Inline Asm** | Still 0 asm!, 1 global_asm! in bare-metal example only |

## Next Version Update Checklist

When a new iceoryx2 version is released:

1. [ ] Clone new version: `python tools/clone_iceoryx2.py v{NEW_VERSION}`
2. [ ] Review release notes for major changes
3. [ ] Identify high-priority chapters (typically FFI, Unsafety, Concurrency)
4. [ ] Update each chapter JSON with new statistics
5. [ ] Update file paths if directory structure changed
6. [ ] Verify code samples still exist and update line numbers
7. [ ] Update this AGENTS.md with new version tracking
8. [ ] Update "Current Status" section at top of this file

## Tips

1. **Use parallel rg commands**: Run multiple statistics gathering commands in parallel for efficiency
2. **Track percentage changes**: Always calculate and document percentage changes from previous version
3. **Verify samples exist**: Before updating, verify code samples still exist at specified locations
4. **Note new patterns**: Document any new language patterns introduced (e.g., let-else, union types)
5. **Document NOT USED**: Explicitly document language features that are intentionally not used (e.g., async/await)
6. **Prioritize high-impact chapters**: FFI, Unsafety, and Concurrency typically have the most changes
7. **Update version_changes section**: Always include from_version, to_version, summary, and key_changes

## References

- [Ferrocene Language Specification](https://rust-lang.github.io/fls/)
- [iceoryx2 Repository](https://github.com/eclipse-iceoryx/iceoryx2)
- [iceoryx2 v0.8.0 Release Notes](cache/repos/iceoryx2/v0.8.0/doc/release-notes/iceoryx2-v0.8.0.md)
