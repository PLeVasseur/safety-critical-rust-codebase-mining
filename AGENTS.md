# FLS Mapping Agent Guide

This document describes the tools, workflows, and data structures for two related mapping efforts:

1. **iceoryx2 FLS Mapping** - Document how iceoryx2 uses Rust language constructs per the Ferrocene Language Specification (FLS)
2. **Coding Standards Mapping** - Map MISRA/CERT safety guidelines to FLS sections using semantic similarity

**Multi-Standard Support:** All verification and embedding tools require a `--standard` parameter.
Valid standards: `misra-c`, `misra-cpp`, `cert-c`, `cert-cpp`

---

## Project Purpose and End Goals

### Ultimate Objective

Identify and prioritize which coding guidelines to write for the iceoryx2 safety-critical codebase.

### How This Works

1. **MISRA-to-FLS Mapping** (Pipeline 2) - Determine how each MISRA C guideline relates to Rust via the FLS
2. **iceoryx2-to-FLS Mapping** (Pipeline 1) - Document which FLS constructs iceoryx2 uses and how frequently
3. **Cross-Reference** (Pipeline 3) - Combine both mappings to prioritize guidelines by relevance to iceoryx2

### Four Output Categories

The MISRA-to-FLS mapping produces four categories that drive different actions:

| Category | Rationale Types | Coding Guideline Action |
|----------|-----------------|-------------------------|
| **Skip List** | `no_equivalent` | None needed - C concept doesn't exist in Rust |
| **Adaptation List** | `direct_mapping`, `partial_mapping` | Adapt MISRA rule for Rust |
| **Alternative List** | `rust_alternative` | Consider Rust-specific guidelines for the alternative mechanism |
| **Prevention List** | `rust_prevents` | Verify prevention completeness; may need guidelines for escape hatches |

### Important Distinction

The mapping answers: **"Does this MISRA rule apply to Rust?"**

This is separate from: **"Does Rust's mechanism need its own coding guidelines?"**

For example:
- MISRA Dir 4.8 (opaque pointers) → `rust_alternative` (Rust uses visibility instead)
- This doesn't mean "no guideline needed" - it means "no MISRA-equivalent guideline needed"
- Rust's visibility system might still need its own guidelines (e.g., "prefer `pub(crate)` over `pub`")

---

## Tool Processing Flow

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SOURCE DATA                                     │
├─────────────────┬─────────────────────────┬─────────────────────────────────┤
│  iceoryx2 repo  │     FLS RST files       │      MISRA/CERT PDFs            │
│  (GitHub)       │     (GitHub)            │      (purchased/scraped)        │
└────────┬────────┴───────────┬─────────────┴──────────────┬──────────────────┘
         │                    │                            │
         ▼                    ▼                            ▼
┌─────────────────┐  ┌─────────────────┐        ┌─────────────────┐
│ PIPELINE 1:     │  │ PIPELINE 2:     │        │ PIPELINE 2:     │
│ iceoryx2 FLS    │  │ FLS Extraction  │        │ Standards       │
│ Mapping         │  │ & Embeddings    │        │ Extraction      │
└────────┬────────┘  └────────┬────────┘        └────────┬────────┘
         │                    │                          │
         ▼                    └──────────┬───────────────┘
┌─────────────────┐                      ▼
│ iceoryx2-fls-   │           ┌─────────────────────────┐
│ mapping/*.json  │           │ Similarity Computation  │
└────────┬────────┘           │ & Mapping Generation    │
         │                    └───────────┬─────────────┘
         │                                ▼
         │                    ┌─────────────────────────┐
         │                    │ coding-standards-fls-   │
         │                    │ mapping/mappings/*.json │
         │                    └───────────┬─────────────┘
         │                                │
         └────────────┬───────────────────┘
                      ▼
           ┌─────────────────────────┐
           │ PIPELINE 3:             │
           │ Cross-Reference &       │
           │ Analysis                │
           └─────────────────────────┘
```

### Pipeline 1: iceoryx2 FLS Mapping

Documents how iceoryx2 codebase uses Rust language constructs as defined by the FLS.

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `clone-iceoryx2` | GitHub | `cache/repos/iceoryx2/v{VERSION}/` | Clone iceoryx2 at specific version tags |
| `extract-fls-sections` | FLS RST files | `fls_section_mapping.json` | Extract FLS section hierarchy |
| `restructure-fls` | `fls_section_mapping.json` | `iceoryx2-fls-mapping/*.json` | Generate chapter JSON skeletons |
| `normalize-fls` | Chapter JSON files | Normalized chapter JSON | Normalize field names and structure |
| `update-fls-counts` | iceoryx2 source + chapter JSON | Updated chapter JSON | Add counts and code samples |
| `validate-fls` | `iceoryx2-fls-mapping/*.json` | Validation report | Schema, coverage, sample validation |

**Run Pipeline 1:**
```bash
cd tools
uv run clone-iceoryx2 --from 0.7.0 --to 0.8.0
uv run extract-fls-sections
uv run normalize-fls
uv run update-fls-counts
uv run validate-fls
```

### Pipeline 2: Coding Standards Mapping

Maps MISRA C/C++ and CERT C/C++ guidelines to FLS sections using semantic similarity.

**Standards Extraction:**

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `extract-misra-rules` | MISRA PDF | `standards/misra_c_2025.json` | Extract MISRA rule listings |
| `scrape-cert-rules` | CERT Wiki | `standards/cert_*.json` | Scrape CERT rule listings |

**Embedding Pipeline:**

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `extract-fls-content` | FLS RST files | `embeddings/fls/chapter_NN.json`, `index.json` | Extract FLS with rubric-categorized paragraphs |
| `extract-misra-text` | MISRA PDF | `cache/misra_c_extracted_text.json` | Extract MISRA guideline full text |
| `generate-embeddings` | Extracted JSON files | `embeddings.pkl`, `paragraph_embeddings.pkl` | Generate section (338) and paragraph (3,733) embeddings |
| `compute-similarity` | Embedding files | `embeddings/similarity/misra_c_to_fls.json` | Compute cosine similarity matrix |
| `orchestrate-embeddings` | (runs above) | All outputs | Convenience script for full pipeline |

**Mapping Generation:**

| Command | Input | Output | Description |
|---------|-------|--------|-------------|
| `sync-fls-mapping` | `embeddings/fls/chapter_NN.json` | Updated `fls_section_mapping.json` | Generate fabricated section entries |
| `map-misra-to-fls` | Similarity + concepts | `mappings/misra_c_to_fls.json` | Generate automated mappings |

**Run Pipeline 2:**
```bash
cd tools
# Option A: Use orchestrator
uv run orchestrate-embeddings --force

# Option B: Run steps manually
uv run extract-fls-content
uv run sync-fls-mapping
uv run generate-embeddings
uv run compute-similarity
uv run map-misra-to-fls

# Validate
uv run validate-standards
uv run validate-synthetic-ids
```

### Pipeline 3: Cross-Reference & Analysis

**Status:** Partially implemented. Existing tools provide basic analysis; end-to-end prioritization workflow pending.

| Command | Purpose | Usage |
|---------|---------|-------|
| `analyze-coverage` | Cross-reference FLS usage across all mappings | `uv run analyze-coverage` |
| `review-mappings` | Interactive/batch review of coding standard mappings | `uv run review-mappings --standard misra-c --interactive` |

**Planned Tools (Not Yet Implemented):**

| Command | Purpose |
|---------|---------|
| `generate-guideline-categories` | Group guidelines by rationale type into four category lists |
| `compute-priority-scores` | Calculate priority based on iceoryx2 FLS usage |
| `generate-writing-plan` | Produce prioritized guideline writing plan |

**Purpose:** Cross-reference iceoryx2-FLS mappings with coding standards mappings to:
1. Categorize guidelines by action needed (skip, adapt, alternative, prevention)
2. Prioritize by frequency of FLS construct usage in iceoryx2
3. Generate an actionable guideline writing plan

See [`docs/future/cross-reference-analysis.md`](docs/future/cross-reference-analysis.md) for detailed design.

### Shared Resources

| File | Location | Description |
|------|----------|-------------|
| `fls_section_mapping.json` | `tools/data/` | Canonical FLS section hierarchy with fabricated sections |
| `fls_id_to_section.json` | `tools/data/` | Reverse lookup from FLS ID to section |
| `synthetic_fls_ids.json` | `tools/data/` | Tracks generated FLS IDs |
| `concept_to_fls.json` | `coding-standards-fls-mapping/` | C concept to FLS ID keyword mappings |
| `misra_rust_applicability.json` | `coding-standards-fls-mapping/` | MISRA ADD-6 Rust applicability data |

---

## Path Safety

### The Problem

When tools accept user-provided paths (e.g., `--output ../cache/file.json`), naive path joining doesn't resolve `..` components:

```python
# Running from tools/ directory:
root = Path("/home/user/project")
user_path = Path("../cache/file.json")
result = root / user_path
# Result: /home/user/project/../cache/file.json
# This path is OUTSIDE the project when traversed!
```

The `..` remains unresolved, and the resulting path escapes the project directory.

### The Fix

All verification tools now use two utilities from `fls_tools.shared`:

1. **`resolve_path(path)`** - Resolves the path relative to cwd, converting `..` to actual directory names
2. **`validate_path_in_project(path, root)`** - Errors if the resolved path is outside the project root

Tools will reject paths that would write outside the project:

```
ERROR: Path '/home/user/other/file.json' is outside project root '/home/user/project'
```

### Recommended Usage

**Prefer `--batch` options** when available - they auto-resolve to correct cache paths:

```bash
uv run record-decision --standard misra-c --batch 4 --guideline "Dir 1.1" ...
uv run merge-decisions --standard misra-c --batch 4 --session 6
uv run apply-verification --standard misra-c --batch 4 --session 6
uv run remediate-decisions --standard misra-c --batch 4 --waiver "..."
```

**Explicit paths still work** - they're resolved and validated:

```bash
# Works - resolved path is within project
uv run verify-batch --standard misra-c --batch 4 --output cache/verification/misra-c/batch4.json

# Works - absolute path within project  
uv run verify-batch --standard misra-c --batch 4 --output /home/user/project/cache/verification/misra-c/batch4.json

# Fails - resolved path escapes project
uv run verify-batch --standard misra-c --batch 4 --output /tmp/batch4.json
# ERROR: Path '/tmp/batch4.json' is outside project root
```

---

## Repository Structure

```
eclipse-iceoryx2-actionanable-safety-certification/
├── AGENTS.md                           # This file
├── README.md
│
├── iceoryx2-fls-mapping/               # Pipeline 1 output: iceoryx2 FLS documentation
│   ├── schema.json                     # JSON Schema for chapter files
│   ├── backup/                         # Backup of files before normalization
│   └── fls_chapter{02-22}_*.json       # 21 chapter mapping files
│
├── coding-standards-fls-mapping/       # Pipeline 2 output: standards to FLS mappings
│   ├── schema/
│   │   ├── batch_report.schema.json
│   │   ├── coding_standard_rules.schema.json
│   │   ├── fls_mapping.schema.json
│   │   └── verification_progress.schema.json
│   ├── standards/                      # Extracted rule listings
│   │   ├── misra_c_2025.json
│   │   ├── misra_cpp_2023.json
│   │   ├── cert_c.json
│   │   └── cert_cpp.json
│   ├── mappings/                       # FLS mappings (deliverables)
│   │   ├── misra_c_to_fls.json
│   │   ├── misra_cpp_to_fls.json
│   │   ├── cert_c_to_fls.json
│   │   └── cert_cpp_to_fls.json
│   ├── verification/                   # Verification progress (per-standard)
│   │   ├── misra-c/
│   │   │   └── progress.json
│   │   ├── misra-cpp/
│   │   ├── cert-c/
│   │   └── cert-cpp/
│   ├── concept_to_fls.json             # C concept to FLS ID mappings
│   └── misra_rust_applicability.json   # MISRA ADD-6 Rust applicability
│
├── embeddings/                         # Extracted content and embeddings
│   ├── fls/
│   │   ├── index.json                  # Chapter listing and statistics
│   │   ├── chapter_01.json             # Per-chapter extracted content
│   │   ├── ...
│   │   ├── chapter_22.json
│   │   ├── embeddings.pkl              # FLS section-level embeddings (338)
│   │   └── paragraph_embeddings.pkl    # FLS paragraph-level embeddings (3,733)
│   ├── misra-c/                        # Per-standard embeddings (kebab-case)
│   │   ├── embeddings.pkl              # Guideline-level embeddings
│   │   ├── query_embeddings.pkl        # Query-level embeddings
│   │   ├── rationale_embeddings.pkl    # Rationale embeddings
│   │   ├── amplification_embeddings.pkl # Amplification embeddings
│   │   └── similarity.json             # Similarity computation results
│   ├── misra-cpp/
│   ├── cert-c/
│   └── cert-cpp/
│
├── cache/                              # Cached data (gitignored)
│   ├── repos/
│   │   ├── iceoryx2/v0.8.0/            # iceoryx2 source at specific versions
│   │   └── fls/                        # FLS RST source files
│   ├── verification/                   # Batch verification reports (per-standard)
│   │   ├── misra-c/
│   │   │   ├── batch{N}_session{M}.json
│   │   │   └── batch{N}_decisions/
│   │   ├── misra-cpp/
│   │   ├── cert-c/
│   │   └── cert-cpp/
│   └── misra_c_extracted_text.json     # Extracted MISRA text
│
└── tools/                              # All tools
    ├── pyproject.toml                  # Package config with entry points
    ├── src/fls_tools/                  # Main package
    │   ├── shared/                     # Shared utilities
    │   │   ├── paths.py                # Path helpers
    │   │   ├── constants.py            # Category codes, thresholds
    │   │   ├── io.py                   # JSON/pickle I/O
    │   │   ├── fls.py                  # FLS chapter loading
    │   │   └── similarity.py           # Search utilities
    │   ├── iceoryx2/                   # Pipeline 1: iceoryx2 FLS mapping
    │   │   ├── clone.py
    │   │   ├── extract.py
    │   │   ├── normalize.py
    │   │   ├── restructure.py
    │   │   ├── update.py
    │   │   └── validate.py
    │   ├── standards/                  # Pipeline 2: Standards to FLS
    │   │   ├── extraction/             # MISRA/CERT extraction
    │   │   ├── embeddings/             # Embedding generation
    │   │   ├── mapping/                # Mapping generation
    │   │   ├── validation/             # Validation scripts
│   │   └── verification/           # Verification workflow
│   │       ├── batch.py            # verify-batch
│   │       ├── apply.py            # apply-verification
│   │       ├── enrich.py           # enrich-fls-matches
│   │       ├── merge.py            # merge-decisions
│   │       ├── progress.py         # check-progress
│   │       ├── record.py           # record-decision
│   │       ├── reset.py            # reset-batch
│   │       ├── reset_verification.py # reset-verification
│   │       ├── scaffold.py         # scaffold-progress
│   │       ├── search.py           # search-fls
│   │       ├── search_deep.py      # search-fls-deep
│   │       ├── recompute.py        # recompute-similarity
│   │       └── batch_check.py      # check-guideline
    │   └── analysis/                   # Pipeline 3: Cross-reference
    │       ├── coverage.py
    │       └── review.py
    └── data/                           # Configuration files
        ├── fls_section_mapping.json    # Canonical FLS hierarchy
        ├── fls_id_to_section.json      # Reverse FLS ID lookup
        └── synthetic_fls_ids.json      # Generated FLS IDs
```

> **Copyright Notice:** The `cache/` directory contains files with copyrighted MISRA content:
> - `cache/misra_c_extracted_text.json` - Full MISRA rationale/amplification text (required for verification)
> - `cache/verification/*.json` - Batch reports with MISRA rationale (delete after verification applied)
> - `cache/verification/batch*_decisions/` - Per-guideline decision files (delete after merge and apply)
> 
> These files are gitignored and must NEVER be committed. Batch reports and decision directories should be deleted immediately after successful application via `apply-verification`.

---

## JSON File Schemas

### Category Codes

FLS content that doesn't have traditional section headings uses a special encoding with negative numbers:

| Code | Name | RST Rubric | Description |
|------|------|------------|-------------|
| `0` | `section` | *(heading)* | Section-level entry (container) |
| `-1` | `general` | *(none)* | Intro text before first rubric |
| `-2` | `legality_rules` | `Legality Rules` | Compiler-enforced rules |
| `-3` | `dynamic_semantics` | `Dynamic Semantics` | Runtime behavior |
| `-4` | `undefined_behavior` | `Undefined Behavior` | UB definitions |
| `-5` | `implementation_requirements` | `Implementation Requirements` | Impl requirements |
| `-6` | `implementation_permissions` | `Implementation Permissions` | Impl permissions |
| `-7` | `examples` | `Examples` | Code examples |
| `-8` | `syntax` | `Syntax` | Syntax block productions |

**Section number encoding:** `X.-2.Y` means "Chapter X, Legality Rules, item Y" (e.g., `8.-2.1` = Chapter 8 Legality Rule 1).

### fls_section_mapping.json

Canonical FLS section hierarchy. Contains:
- Standard sections (e.g., `8.1`, `8.2`)
- Fabricated sections for rubric content (keys starting with `_`, e.g., `_legality_rules`)

```json
{
  "8": {
    "title": "Statements",
    "fls_id": "fls_hdwwrsyunir",
    "sections": {
      "let_statements": {
        "fls_section": "8.1",
        "title": "Let Statements",
        "fls_id": "fls_yiw26br6wj3g"
      },
      "_legality_rules": {
        "fls_section": "8.-2",
        "title": "Legality Rules",
        "category": -2,
        "fls_id": null,
        "paragraph_count": 21,
        "subsections": {
          "from_fls_yiw26br6wj3g": {
            "fls_section": "8.-2.1",
            "title": "Let Statements",
            "category": -2,
            "fls_id": "fls_yiw26br6wj3g",
            "paragraph_ids": ["fls_abc123", "fls_def456"]
          }
        }
      }
    }
  }
}
```

### embeddings/fls/ Structure

Split chapter files with rubric-categorized paragraphs.

**index.json:**
```json
{
  "source": "FLS RST files",
  "extraction_date": "2025-12-31",
  "category_codes": {
    "0": "section", "-1": "general", "-2": "legality_rules", ...
  },
  "chapters": [
    {"chapter": 1, "title": "General", "fls_id": "fls_...", "file": "chapter_01.json"}
  ],
  "aggregate_statistics": {
    "total_sections": 338,
    "total_paragraphs": 4054,
    "paragraphs_by_category": {"-2": 3256, "-3": 355, ...}
  }
}
```

**chapter_NN.json:**
```json
{
  "chapter": 15,
  "title": "Ownership and Destruction",
  "fls_id": "fls_ronnwodjjjsh",
  "sections": [
    {
      "fls_id": "fls_v5x85lt5ulva",
      "title": "References",
      "category": 0,
      "level": 2,
      "content": "cleaned text for embeddings...",
      "parent_fls_id": "fls_ronnwodjjjsh",
      "sibling_fls_ids": ["fls_svkx6szhr472", ...],
      "rubrics": {
        "-2": {
          "paragraphs": {
            "fls_ev4a82fdhwr8": "A reference shall point to an initialized referent.",
            "fls_i1ny0k726a4a": "While a mutable reference is active, no other reference shall..."
          }
        },
        "-4": {
          "paragraphs": {
            "fls_eT1hnLOx6vxk": "It is undefined behavior to access a value through aliasing..."
          }
        }
      }
    }
  ]
}
```

**Quick lookup:**
```python
import json

with open('embeddings/fls/chapter_15.json') as f:
    chapter = json.load(f)

section = next(s for s in chapter['sections'] if s['fls_id'] == 'fls_v5x85lt5ulva')

# Get legality rules (category -2)
for pid, text in section['rubrics'].get('-2', {}).get('paragraphs', {}).items():
    print(f"{pid}: {text[:80]}...")

# Get UB definitions (category -4)
for pid, text in section['rubrics'].get('-4', {}).get('paragraphs', {}).items():
    print(f"{pid}: {text[:80]}...")
```

### iceoryx2-fls-mapping/ Schema

Chapter files documenting iceoryx2's use of FLS constructs. Schema: `iceoryx2-fls-mapping/schema.json`

**Required top-level fields:**

| Field | Type | Description |
|-------|------|-------------|
| `chapter` | integer | FLS chapter number (1-25) |
| `title` | string | Chapter title from FLS |
| `fls_url` | string | URL to FLS chapter |
| `fls_id` | string | FLS chapter identifier |
| `repository` | string | Always `"eclipse-iceoryx/iceoryx2"` |
| `version` | string | Semver version analyzed |
| `analysis_date` | string | ISO 8601 date |
| `sections` | object | FLS section mappings |

**Section structure:**
```json
{
  "ownership": {
    "fls_section": "15.1",
    "fls_ids": ["fls_svkx6szhr472"],
    "description": "Ownership is a property of values...",
    "status": "demonstrated",
    "count": 42,
    "samples": [
      {
        "file": "iceoryx2-bb/posix/src/mutex.rs",
        "line": [186, 187, 188],
        "code": "pub struct MutexGuard<'a, T> { ... }",
        "purpose": "RAII guard for mutex unlock"
      }
    ]
  }
}
```

### coding-standards-fls-mapping/ Schema

**standards/*.json** - Rule listings per standard
**mappings/*.json** - FLS mappings with per-context verification (v2 schema):

**v1 Structure (legacy):**
```json
{
  "schema_version": "1.0",
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  "applicability_all_rust": "direct",
  "applicability_safe_rust": "not_applicable",
  "fls_rationale_type": "direct_mapping",
  "confidence": "medium",
  "accepted_matches": [...],
  "rejected_matches": []
}
```

**v2 Structure (current):**
```json
{
  "schema_version": "2.0",
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  "all_rust": {
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [
      {
        "fls_id": "fls_xxx",
        "category": 0,
        "fls_title": "Type Cast Expressions",
        "score": 0.65,
        "reason": "Per FLS: 'A cast is legal when...' This directly addresses MISRA's concern."
      }
    ],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  },
  "safe_rust": {
    "applicability": "no",
    "adjusted_category": "n_a",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [
      {
        "fls_id": "fls_yyy",
        "category": 0,
        "fls_title": "Type Coercion",
        "score": 0.58,
        "reason": "Safe Rust prevents arbitrary pointer-to-function casts via type system."
      }
    ],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "Safe Rust has no raw pointers or function pointer casts."
  }
}
```

### Match Semantics

#### Stable Definitions

| Field | Meaning |
|-------|---------|
| `accepted_matches` | FLS sections **relevant to understanding** how Rust handles the concern this MISRA rule addresses |
| `rejected_matches` | FLS sections **considered during verification** but determined to be tangential or not useful |

These definitions are **stable across all rationale types**.

#### What Goes in `accepted_matches`

Include an FLS section if someone working on coding guidelines would benefit from reading it to understand how Rust handles this concern.

| Rationale Type | `accepted_matches` Contains |
|----------------|----------------------------|
| `direct_mapping` | FLS sections with equivalent rules/constraints |
| `partial_mapping` | FLS sections covering the parts that map |
| `rust_alternative` | FLS sections showing Rust's alternative mechanism |
| `rust_prevents` | FLS sections showing HOW Rust prevents the issue |
| `no_equivalent` | FLS sections explaining WHY the concept doesn't exist |

#### What Goes in `rejected_matches`

Include when:
- FLS section appeared in similarity search but isn't useful for understanding the concern
- Section is too generic (e.g., "Expressions" for a specific operator rule)
- Section is tangentially related but doesn't help someone understand the MISRA concern

#### Exception: Meta-Information

FLS sections that are meta-information about the FLS document itself (e.g., "Scope", "Extent", "Versioning" from Chapter 1) should go in `rejected_matches` even if they appeared in search, because they describe the FLS document rather than language constructs that code uses.

#### Why Both Fields Serve One Purpose

`accepted_matches` serves two purposes simultaneously:
1. **Applicability documentation** - Explains why/how the rule applies (or doesn't) to Rust
2. **Cross-reference target** - Links to iceoryx2-FLS mapping for prioritization

Both purposes need the same FLS sections, so one field serves both needs.

---

## iceoryx2 FLS Mapping Guide

### Current Status

**All chapters updated to v0.8.0** - Completed 2025-12-30

- 21 chapter JSON files (chapters 2-22)
- 0 MUST_BE_FILLED markers remaining
- All files pass schema validation
- Chapter 1 (General) intentionally excluded (metadata, not language constructs)

Next update required when iceoryx2 v0.9.0 or later is released.

### Update Workflow

When a new iceoryx2 version is released:

#### 1. Clone Repositories

```bash
cd tools
uv run clone-iceoryx2 --from 0.8.0 --to 0.9.0
```

This clones both versions to `cache/repos/iceoryx2/v{VERSION}/` for comparison.

#### 2. Review Changelog

Check `cache/repos/iceoryx2/v{NEW_VERSION}/doc/release-notes/` for:
- Directory structure changes
- New language features used
- New crates added
- MSRV changes

#### 3. Update Each Chapter

For each chapter, gather statistics using `rg` (ripgrep):

```bash
cd cache/repos/iceoryx2/v{NEW_VERSION}

# Count pattern occurrences
rg -c 'PATTERN' --type rust 2>/dev/null | awk -F: '{sum+=$2} END {print sum}'

# Find sample code with line numbers
rg -n 'PATTERN' --type rust | head -5
```

**Common patterns by chapter:**

| Chapter | Patterns |
|---------|----------|
| 6 - Expressions | `\bmatch\b`, `\bif let\b`, `\bunsafe\s*\{`, `\bloop\s*\{`, `\?` |
| 7 - Values | `\bconst\s+[A-Z]`, `\bstatic\s+mut\b`, `\bMaybeUninit\b` |
| 9 - Functions | `\bpub\s+fn\b`, `\bunsafe\s+fn\b`, `\bextern\s+"C"\s+fn\b` |
| 15 - Ownership | `impl\s+Drop\s+for`, `ManuallyDrop`, `PhantomData` |
| 17 - Concurrency | `\bAtomic`, `\bOrdering::`, `unsafe\s+impl\s+Send` |
| 19 - Unsafety | `\bunsafe\s*\{`, `\bunsafe\s+fn\b`, `\bunion\b` |
| 20 - Macros | `macro_rules!`, `#\[proc_macro`, `#\[macro_export` |
| 21 - FFI | `extern\s+"C"\s*\{`, `#\[no_mangle\]`, `#\[repr\(C\)\]` |

#### 4. Update JSON Files

Update each chapter's JSON with:
- New statistics in `statistics` field
- Updated `version` and `analysis_date`
- New code samples (verify paths exist)
- `version_changes` section documenting changes

#### 5. Validate

```bash
cd tools
uv run validate-fls
```

### Code Sample Guidelines

**Acceptable sources:** Production code in `/src/` directories only:
- `iceoryx2/src/`, `iceoryx2-bb/*/src/`, `iceoryx2-pal/*/src/`, etc.

**NOT acceptable:** Tests, examples, benchmarks, doc comments.

**Quality requirements:**
- Code >20 characters
- Meaningful `purpose` field (not "Demonstrates X...")
- Accurate line numbers

**Features only in tests/examples:** Set `status` to `not_used` or `deliberately_avoided` with `samples_waiver`.

### Validation

```bash
cd tools
uv run validate-fls                                    # All checks
uv run validate-fls --file=fls_chapter15_ownership_destruction.json
uv run validate-fls --audit-samples                    # Sample quality audit
```

**Checks performed:**
- Schema validation
- MUST_BE_FILLED detection
- Sample path validation
- FLS coverage (all sections documented)
- Section hierarchy validation
- Minimum 3 samples per section

### Version History Example: v0.7.0 to v0.8.0

| Metric | v0.7.0 | v0.8.0 | Change |
|--------|--------|--------|--------|
| unsafe blocks | 1,702 | 2,372 | +39% |
| unsafe fn | 1,302 | 1,763 | +35% |
| extern "C" fn | 17 | 630 | +3606% |
| union types | 0 | 42 | new |

**Key changes:** FFI layer expansion (`iceoryx2-ffi/c`), logger restructuring, no_std support.

---

## Coding Standards Mapping Guide

### Current Status (2025-12-31)

**MISRA C:2025 Mapping - Complete (Draft):**
- All 228 guidelines processed with MISRA ADD-6 Rust applicability
- 196 guidelines with FLS matches, 32 without
- 11 high-confidence entries (manually verified)
- 217 medium-confidence entries (automated, require LLM verification workflow)

**Confidence Levels:**
- `medium` = Generated automatically by `map_misra_to_fls.py`
- `high` = After completing the MISRA to FLS Verification Workflow below

**Other Standards:** Scaffolds only (MISRA C++, CERT C/C++)

### MISRA to FLS Verification Workflow

The verification workflow uses a 4-phase process with dedicated tooling.

**Schema Version:** The verification workflow now uses **v2.0 schema** with per-context verification. Each guideline is verified independently for two contexts:
- **`all_rust`** - Applicability when using all of Rust (including unsafe)
- **`safe_rust`** - Applicability when restricted to safe Rust only

This means each guideline requires **8 searches** (4 per context) instead of 4.

#### Phase 0: Check Progress

Before starting, run `check-progress` to determine current state:

```bash
cd tools
uv run check-progress --standard misra-c
uv run check-progress --standard misra-c --workers 4  # Adjust worker count for parallel mode
```

This shows:
- Last session ID and next session ID to use
- Current batch and its status
- Per-context verification progress (all_rust: X/Y, safe_rust: X/Y)
- Whether a batch report exists in `cache/verification/`
- Whether a decisions directory exists (for parallel mode)
- Progress from decision files (valid/invalid counts)
- Schema version information (v1/v2 entry counts)
- Suggested worker assignments for remaining guidelines
- If resuming, which guideline to continue from
- Suggested command for Phase 1 (if batch report doesn't exist)

**Example output:**
```
============================================================
VERIFICATION PROGRESS: misra-c
============================================================

Current batch: 1 (High-score direct mappings)
Status: in_progress

Guideline Progress:
  Dir 4.3:  all_rust ✓  safe_rust ✓
  Dir 5.1:  all_rust ✓  safe_rust ○
  Rule 5.1: all_rust ○  safe_rust ○

Summary:
  all_rust:  5/20 verified (25%)
  safe_rust: 3/20 verified (15%)
  Both complete: 3/20 (15%)
```

**Crash recovery:** If a session was interrupted, `check-progress` will detect existing work in either the batch report or decisions directory and indicate where to resume.

#### Phase 1: Data Gathering

If no batch report exists, run `verify-batch` to generate one:

```bash
cd tools
uv run verify-batch \
    --standard misra-c \
    --batch BATCH_ID \
    --session SESSION_ID \
    --mode llm \
    --schema-version 2.0
```

**What it extracts:**
- Similarity matches (section and paragraph) above thresholds
- MISRA rationale from extracted text
- Wide-shot FLS content (matched sections + siblings + all rubrics)
- Current mapping state

All guidelines start with a scaffolded `verification_decision` structure with nested `all_rust` and `safe_rust` contexts (fields set to `null`/empty).
See `coding-standards-fls-mapping/schema/batch_report.schema.json` for required fields.

**Output modes:**
- `--mode llm`: Full JSON optimized for LLM consumption
- `--mode human`: Markdown summary for quick review

**Schema version:**
- `--schema-version 2.0` (default): Generates v2 batch reports with per-context verification decisions
- `--schema-version 1.0`: Legacy flat structure (not recommended for new verification)

**Thresholds** (configurable via CLI):

| Option | Default | Description |
|--------|---------|-------------|
| `--section-threshold` | 0.5 | Minimum section similarity score |
| `--paragraph-threshold` | 0.55 | Minimum paragraph similarity score |

**Failure conditions:** Script fails immediately if `cache/misra_c_extracted_text.json` is missing.

#### Parallel Verification Workflow (Optional)

For large batches, verification can be parallelized across multiple workers. Each worker processes a subset of guidelines independently, writing decisions to a shared directory.

##### Determining Worker Count

Before starting parallel verification, ask the user how many workers they want to use:

> "Batch N has X guidelines to verify. How many parallel workers would you like to use?
> 
> Recommendations:
> - **3 workers** - Good balance, recommended for most cases
> - **4 workers** - More parallelism
> - **2 workers** - Conservative, less coordination
> 
> Enter number of workers (default: 3):"

Then run `check-progress --standard misra-c --workers N` to show the specific guideline assignments for each worker.

##### Setup

```bash
cd tools

# 1. Generate batch report (becomes READ-ONLY reference)
uv run verify-batch \
    --standard misra-c \
    --batch 4 \
    --session 6 \
    --mode llm

# 2. Create decisions directory
mkdir -p cache/verification/misra-c/batch4_decisions

# 3. Check worker assignments
uv run check-progress --standard misra-c --workers 3
```

##### Recording Decisions (Parallel-Safe)

Use `--batch` to write decisions to individual files (enables parallel verification). **v2 requires `--context` to specify which context is being verified:**

```bash
uv run record-decision \
    --standard misra-c \
    --batch 4 \
    --guideline "Dir 1.1" \
    --context all_rust \
    --decision accept_with_modifications \
    --applicability yes \
    --adjusted-category advisory \
    --rationale-type direct_mapping \
    --confidence high \
    --search-used "550e8400-e29b-41d4-a716-446655440000:search-fls-deep:Dir 1.1:5" \
    --search-used "a1b2c3d4-5678-90ab-cdef-1234567890ab:search-fls:ABI implementation:10" \
    --search-used "b2c3d4e5-6789-01ab-cdef-2345678901ab:search-fls:rust ABI extern:10" \
    --search-used "c3d4e5f6-7890-12ab-cdef-3456789012ab:search-fls:calling convention:10" \
    --accept-match "fls_abc123:ABI:0:0.64:FLS states X addressing MISRA concern Y"
```

Each guideline has a single decision file (e.g., `Dir_1.1.json`) containing both contexts. Recording a decision for one context preserves the other context's existing data (or scaffolds it as null if not yet recorded).

**New v2 required parameters:**
- `--context {all_rust,safe_rust}`: Which context this decision applies to
- `--applicability {yes,no,partial}`: Whether the guideline applies in this context
- `--adjusted-category {required,advisory,recommended,disapplied,implicit,n_a}`: MISRA adjusted category for Rust

##### Progress Tracking

```bash
# Check progress (counts valid decision files)
uv run check-progress --standard misra-c

# Validate decision files
uv run validate-decisions \
    --decisions-dir cache/verification/misra-c/batch4_decisions/ \
    --batch-report cache/verification/misra-c/batch4_session6.json
```

##### Merging Decisions (Before Phase 3)

After all workers complete, merge decisions back into the batch report:

```bash
uv run merge-decisions \
    --standard misra-c \
    --batch 4 \
    --session 6 \
    --validate
```

This populates `verification_decision` fields in the batch report and aggregates any `proposed_applicability_change` entries for Phase 3 review.

**Duplicate UUID validation:** Before merging, the tool checks all decision files for duplicate `search_id` values. If any UUID appears in multiple guidelines' decisions, the merge fails with an error listing the conflicts. This enforces that each search execution can only be used by one guideline.

**Incremental merge:** Can merge partial progress (e.g., 30/54 decisions) and continue later.

#### Phase 2: Analysis & Decision (LLM)

If resuming an interrupted session, output "Resuming from Rule X.Y (N/M complete)" at the start.

**IMPORTANT:** Process guidelines ONE AT A TIME. Complete all 4 searches and record the decision for each guideline before moving to the next. Do not batch searches across multiple guidelines or reuse search results. See "Search Protocol Enforcement" below for details.

Process the batch report JSON and for each guideline:

1. **Review extracted data** in the batch report
2. **Investigate further as needed** using these sources:

| Source | Path | Purpose |
|--------|------|---------|
| FLS Chapter Files | `embeddings/fls/chapter_NN.json` | Full section content with all rubrics |
| FLS Section Mapping | `tools/data/fls_section_mapping.json` | Section hierarchy and fabricated sections |
| MISRA Extracted Text | `cache/misra_c_extracted_text.json` | Full MISRA rationale and amplification |
| MISRA Rust Applicability | `coding-standards-fls-mapping/misra_rust_applicability.json` | MISRA ADD-6 Rust applicability data |
| Concept to FLS | `coding-standards-fls-mapping/concept_to_fls.json` | C concept to FLS ID keyword mappings |
| Current Mappings | `coding-standards-fls-mapping/mappings/misra_c_to_fls.json` | Current mapping state |
| Standards Definitions | `coding-standards-fls-mapping/standards/misra_c_2025.json` | MISRA rule definitions |
| Similarity Results | `embeddings/similarity/misra_c_to_fls.json` | Full similarity scores |

3. **Validate batch membership** before starting work on a guideline:

   ```bash
   uv run check-guideline --standard misra-c --guideline "Rule X.Y" --batch N
   ```

   This confirms the guideline is in the expected batch and shows its current status.
   
   **Success output:**
   ```
   OK: Guideline 'Rule 17.12' is in batch 2
     Batch: 2 (Not applicable)
     Batch status: pending
     Guideline status: pending
   ```
   
   **If batch mismatch:**
   ```
   ERROR: Guideline 'Rule 15.4' is not in batch 2. Actual batch: 1 (High-score direct mappings)
     Batch 1 status: completed
   ```
   
   If the guideline is not in the expected batch, do NOT proceed. Skip to the next guideline.

4. **Search FLS for relevant content:**

   **Required search protocol** (mandatory for each guideline):
   
   ```bash
   # Step 1: Deep search (always first)
   uv run search-fls-deep --standard misra-c --guideline "Rule X.Y"
   
   # Step 2: C/MISRA terminology query
   uv run search-fls --query "<C concepts from rule text>" --top 10
   
   # Step 3: Rust terminology query  
   uv run search-fls --query "<Rust equivalent concepts>" --top 10
   
   # Step 4: Additional angles as needed (safety concepts, related mechanisms)
   uv run search-fls --query "<semantic/safety concepts>" --top 10
   ```

   **Query style guide** (use multiple angles to maximize coverage):
   
   | Style | Description | Example |
   |-------|-------------|---------|
   | C/MISRA terminology | C language concepts from rule text | `"const pointer parameter mutable"` |
   | Rust terminology | Rust-specific concepts | `"borrow shared exclusive reference"` |
   | Safety/semantic | Focus on underlying concern | `"mutation prevention immutable"` |
   | Related mechanisms | Rust features addressing concern differently | `"interior mutability Cell RefCell"` |
   | Error/UB concepts | What goes wrong if violated | `"undefined behavior dangling"` |

   **Why multi-search matters:**
   
   Single searches miss relevant FLS content. For example, Rule 8.9 (block scope):
   - C-terminology search found: `Binding Scopes`, `Item Scope`
   - Rust-terminology search additionally found: `Drop Scopes` - directly relevant since MISRA wants minimal scope for cleanup, and Rust's drop scopes provide deterministic destruction at block boundaries
   
   **Additional methods** if search tools are not sufficient:
   - Read FLS chapter files directly (`embeddings/fls/chapter_NN.json`)
   - Grep across FLS content for keywords
   - Check `tools/data/fls_section_mapping.json` for section hierarchy
   - Check `coding-standards-fls-mapping/concept_to_fls.json` for known concept mappings

#### Decision Summary Format

For each guideline processed, output a structured analysis summary before recording decisions. This provides visibility into the reasoning and creates an audit trail.

**Format:**

```
## Rule X.Y - <Title>

**MISRA Concern:** <1-2 sentence summary of what problem this rule addresses in C>

**Rust Analysis:** <2-4 sentences explaining how Rust handles this concern, with FLS references where relevant>

| Context | Applicability | Category | Rationale Type | Key FLS |
|---------|---------------|----------|----------------|---------|
| all_rust | <yes/no/partial> | <category> | <rationale_type> | <fls_id: brief reason> |
| safe_rust | <yes/no/partial> | <category> | <rationale_type> | <fls_id: brief reason> |
```

**Example - Both contexts identical (Batch 2 style):**

```
## Rule 8.8 - The static storage class specifier shall be used in all declarations of objects and functions that have internal linkage

**MISRA Concern:** In C, the `static` keyword must be used consistently for internal linkage because `extern` on a previously-declared-static item confusingly inherits the static linkage rather than creating external linkage.

**Rust Analysis:** Rust has no `static` storage class specifier for linkage control. Instead, visibility modifiers (`pub`, `pub(crate)`, private-by-default) control access. Items are private by default (equivalent to internal). The keyword `static` in Rust means a global variable with static lifetime, not internal linkage.

| Context | Applicability | Category | Rationale Type | Key FLS |
|---------|---------------|----------|----------------|---------|
| all_rust | no | n_a | `no_equivalent` | `fls_jdknpu3kf865`: Visibility - private by default |
| safe_rust | no | n_a | `no_equivalent` | `fls_jdknpu3kf865`: Visibility - private by default |
```

**Example - Contexts differ:**

```
## Rule 11.3 - A cast shall not be performed between a pointer to object type and a pointer to a different object type

**MISRA Concern:** Casting between incompatible pointer types can violate alignment requirements and type aliasing rules, causing undefined behavior.

**Rust Analysis:** Safe Rust prohibits arbitrary pointer casts - references are typed and the borrow checker enforces aliasing rules. In unsafe Rust, raw pointer casts via `as` or `transmute` are possible but require explicit `unsafe` blocks.

| Context | Applicability | Category | Rationale Type | Key FLS |
|---------|---------------|----------|----------------|---------|
| all_rust | yes | advisory | `direct_mapping` | `fls_1qhsun1vyarz`: Type Cast Expressions - raw pointer casts |
| safe_rust | no | n_a | `rust_prevents` | `fls_ppwBSNQ2W7jf`: Borrow checker prevents aliasing violations |
```

**Guidelines:**
- Keep MISRA Concern to 1-2 sentences focusing on the safety issue
- Rust Analysis should explain the mechanism, not just state the decision
- Both contexts must be shown even when identical
- Key FLS column: use format `fls_id: brief justification` (full quotes go in the recorded decision)
- Output this summary BEFORE running the `record-decision` commands

#### Search Protocol Enforcement

**CRITICAL: Each guideline MUST have its own 4 searches with results analyzed specifically for that guideline.**

DO NOT:
- Run searches for multiple guidelines, then use the combined results to inform multiple decisions
- "Double-dip" by using the same search output to justify matches for different guidelines
- Batch deep searches for multiple guidelines then share follow-up search results
- Record decisions for multiple guidelines after a shared set of searches

DO:
- Complete all 4 searches for ONE guideline
- Analyze the results specifically for that guideline's concerns
- Record the decision immediately after completing all 4 searches
- Then move to the next guideline and repeat

**Example of WRONG approach:**
```
# WRONG: Batching searches then using results for multiple guidelines
search-fls-deep Rule 10.1
search-fls-deep Rule 10.2  
search-fls-deep Rule 10.3
search-fls "type conversion"  # Uses this result for all 3 rules
record-decision Rule 10.1    # Based on shared search results
record-decision Rule 10.2    # Based on same shared results
record-decision Rule 10.3    # Based on same shared results
```

**Example of CORRECT approach:**
```
# CORRECT: Complete one rule at a time with dedicated analysis
search-fls-deep Rule 10.1
search-fls "essential type operand inappropriate" 
search-fls "rust type system operator requirements"
search-fls "implicit conversion promotion safety"
# Analyze these results for Rule 10.1 specifically
record-decision Rule 10.1

search-fls-deep Rule 10.2
search-fls "character type arithmetic expression"
search-fls "rust char unicode operations"
search-fls "char integer conversion safety"
# Analyze these results for Rule 10.2 specifically
record-decision Rule 10.2
```

**Rationale:** Each MISRA rule addresses specific concerns. Even thematically related rules have nuances that require dedicated analysis of search results in the context of that specific rule. Using the same search output for multiple guidelines leads to:
- Missing rule-specific FLS content that would be found with tailored queries
- Generic/shallow justifications that don't address the specific rule's concerns
- Lower quality mappings that may need rework

#### Search UUID Reuse Rules

Each search tool execution generates a unique UUID. The `merge-decisions` tool validates UUID usage with these rules:

| Scenario | Allowed? | Reason |
|----------|----------|--------|
| `search-fls-deep` UUID shared between `all_rust` and `safe_rust` of same guideline | ✓ Yes | Deep search is guideline-specific, returns same results for both contexts |
| `search-fls` UUID shared between `all_rust` and `safe_rust` of same guideline | ✗ No | Keyword queries should be context-specific (different terminology for safe vs unsafe) |
| Any UUID shared across different guidelines | ✗ No | Each guideline requires its own dedicated searches |

**Why context-specific keyword searches matter:**

For the same MISRA rule, the `all_rust` and `safe_rust` contexts often need different search angles:
- `all_rust`: May search for "unsafe pointer transmute FFI" 
- `safe_rust`: May search for "type coercion borrow checker prevention"

Reusing a keyword search UUID between contexts suggests the verifier didn't perform context-tailored searches.

#### Batch Membership Validation

The `record-decision` tool validates that the guideline belongs to the specified batch before writing. This is a safety net to prevent recording decisions to the wrong batch directory.

**If `record-decision` fails with a batch mismatch error:**

```
ERROR: Guideline 'Rule 15.4' is not in batch 2. Actual batch: 1 (High-score direct mappings)
```

This means:
1. The guideline was incorrectly included in the current batch's work
2. All 4 searches performed for this guideline are wasted (cannot reuse UUIDs)
3. The guideline must be verified when its actual batch is processed

**Recovery steps:**
1. Note which guideline caused the error
2. Do NOT attempt to record the decision to the correct batch (search UUIDs were generated for the wrong context)
3. Continue with the next guideline in the current batch
4. The skipped guideline will be properly verified when its actual batch is processed

**Prevention:** Always run `check-guideline` before starting the 4-search protocol for each guideline.

5. **Make decisions:**
   - Accept matches with score and detailed reason (quote FLS paragraphs)
   - Reject matches above threshold with explanation
   - **May propose FLS sections not in similarity results** - clearly document why in the `reason` field

6. **Flag applicability changes** (do not apply yet):
   
   When analysis suggests an applicability change is warranted:
   - In the guideline's `verification_decision`, set `proposed_applicability_change`:
     ```json
     "proposed_applicability_change": {
       "field": "applicability_all_rust",
       "current_value": "direct",
       "proposed_value": "rust_prevents",
       "rationale": "Rust's ownership system prevents this issue entirely. See FLS fls_xxx."
     }
     ```
   - The change is also recorded in the top-level `applicability_changes` array for Phase 3 review
   
   All changes remain in the batch report (`cache/verification/`) until approved in Phase 3.

7. **Record decisions** using the `record-decision` tool:

   ```bash
   uv run record-decision \
       --standard misra-c \
       --batch 4 \
       --guideline "Dir 1.1" \
       --context all_rust \
       --decision accept_with_modifications \
       --applicability yes \
       --adjusted-category advisory \
       --rationale-type direct_mapping \
       --confidence high \
       --search-used "550e8400-e29b-41d4-a716-446655440000:search-fls-deep:Dir 1.1:5" \
       --search-used "a1b2c3d4-5678-90ab-cdef-1234567890ab:search-fls:ABI implementation:10" \
       --search-used "b2c3d4e5-6789-01ab-cdef-2345678901ab:search-fls:rust ABI extern:10" \
       --search-used "c3d4e5f6-7890-12ab-cdef-3456789012ab:search-fls:calling convention:10" \
       --accept-match "fls_abc123:Section Title:0:0.65:FLS states X which addresses MISRA concern Y" \
       --reject-match "fls_xyz789:Other Section:-1:0.55:Not relevant - discusses Z instead" \
       --notes "Optional notes about the decision"
   ```

   **v2 Required Parameters:**
   - `--context {all_rust,safe_rust}`: Which context this decision applies to
   - `--applicability {yes,no,partial}`: Whether the guideline applies in this context
   - `--adjusted-category`: MISRA adjusted category for Rust (`required`, `advisory`, `recommended`, `disapplied`, `implicit`, `n_a`)

   **Search-used format:** `search_id:tool:query:result_count`
   - `search_id`: UUID4 from search tool output (required for new decisions)
   - `tool`: Search tool name (search-fls, search-fls-deep, etc.)
   - `query`: The search query or guideline ID
   - `result_count`: Number of results returned

   Search tools now output a UUID at the start of their output. Copy this UUID
   when recording decisions to ensure each search is uniquely tracked. At merge
   time, duplicate UUIDs across different guidelines will cause a hard failure.

   **Match format:** `fls_id:fls_title:category:score:reason`
   - `fls_id`: FLS identifier (e.g., `fls_abc123`)
   - `fls_title`: Human-readable title (e.g., "Type Cast Expressions")
   - `category`: Integer category code (0=section, -2=legality_rules, etc.)
   - `score`: Similarity score 0-1
   - `reason`: Justification text (may contain colons)

   **With applicability change proposal:**

   ```bash
   uv run record-decision \
       --standard misra-c \
       --batch 4 \
       --guideline "Rule 11.1" \
       --context all_rust \
       --decision accept_with_modifications \
       --applicability yes \
       --adjusted-category advisory \
       --rationale-type rust_prevents \
       --confidence high \
       --search-used "uuid1:search-fls-deep:Rule 11.1:5" \
       --search-used "uuid2:search-fls:type conversion pointer:10" \
       --search-used "uuid3:search-fls:rust type cast safety:10" \
       --search-used "uuid4:search-fls:unsafe transmute:10" \
       --accept-match "fls_xxx:Type Safety:0:0.70:Rust type system prevents this" \
       --propose-change "applicability_all_rust:direct:rust_prevents:Rust's type system prevents unsafe conversions"
   ```

   **Options:**
   - `--dry-run`: Preview changes without writing to file
   - `--propose-change`: Format is `field:current_value:proposed_value:rationale`

   **Required fields** (validated against `decision_file.schema.json`):
   - `--context`: Which context (all_rust or safe_rust)
   - `--decision`: "accept_with_modifications", "accept_no_matches", "accept_existing", "reject", or "pending"
   - `--applicability`: "yes", "no", or "partial"
   - `--adjusted-category`: MISRA adjusted category for Rust
   - `--rationale-type`: "direct_mapping", "rust_alternative", "rust_prevents", "no_equivalent", or "partial_mapping"
   - `--confidence`: "high", "medium", or "low"
   - `--accept-match`: At least one FLS match (unless `--force-no-matches`)
   - `--search-used`: At least 4 search tool records (each with `search_id`, `tool`, `query`, `result_count`)
   - `--notes`: Additional notes (optional)

**Crash recovery:** If the session is interrupted, the batch report in `cache/verification/` preserves all completed work. Run `check-progress` to see where to resume.

#### Phase 3: Review & Approval (Human)

At the end of Phase 2, the LLM presents a summary of all proposed applicability changes:

```
## Proposed Applicability Changes

| Guideline | Field | Current | Proposed | Rationale |
|-----------|-------|---------|----------|-----------|
| Rule 21.3 | applicability_all_rust | direct | rust_prevents | [brief reason] |
```

Human reviews and confirms verbally (e.g., "approve all", "approve Rule 21.3, reject Rule 21.5").

The LLM then updates the batch report JSON:
- Sets `approved: true` or `approved: false` for each entry in `applicability_changes`
- Confirms batch is ready for Phase 4

#### Phase 4: Apply Changes

Run `apply-verification` to commit verified decisions:

```bash
cd tools
uv run apply-verification \
    --standard misra-c \
    --batch BATCH_ID \
    --session SESSION_ID \
    --apply-applicability-changes  # Only include if changes were approved
```

**Actions:**
- Updates `misra_c_to_fls.json` with verified mappings (`confidence: "high"`)
- Updates `verification_progress.json` with verified status and session
- Runs validation scripts automatically

**Options:**
- `--dry-run`: Show changes without writing files
- `--skip-validation`: Skip running validation after changes

#### Phase 5: Cleanup

After `apply-verification` completes successfully:

1. **Verify application was successful:**
   ```bash
   uv run check-progress --standard misra-c
   ```
   Confirm the batch shows as `completed` with the expected number of verified guidelines.

2. **Spot-check the mapping file:**
   ```bash
   # Verify a sample guideline has confidence: "high"
   grep -A10 '"Rule X.Y"' ../coding-standards-fls-mapping/mappings/misra_c_to_fls.json
   ```

3. **Report results to user:**
   
   Output a summary, for example:
   > "Batch 3 verification successfully applied:
   > - 38 guidelines now have `confidence: high`
   > - `verification_progress.json` updated (Batch 3 status: completed)
   > - Spot-check: Rule 21.3 shows high confidence with 4 accepted FLS matches"

4. **Prompt for cleanup:**
   
   Batch reports and decision directories contain copyrighted MISRA rationale text extracted from the MISRA PDF and must not be retained after verification is complete.
   
   Prompt the user:
   > "The following files contain copyrighted MISRA text:
   > - `cache/verification/batch3_session5.json` (batch report)
   > - `cache/verification/batch3_decisions/` (decision files, if exists)
   > 
   > Shall I delete them?"
   
   **Wait for explicit user approval before deleting.**

5. **Upon approval, delete the files:**
   ```bash
   rm cache/verification/misra-c/batchN_sessionM.json
   rm -rf cache/verification/misra-c/batchN_decisions/
   ```

#### Verification Guidelines

1. **Applicability changes require explicit approval:** If analysis suggests changing `applicability_all_rust`, `applicability_safe_rust`, or `fls_rationale_type` from existing values:
   - **DO NOT** make the change during normal verification
   - **DO** track the proposed change with rationale
   - **DO** include all proposed changes in a summary report at the end of the verification session
   - **WAIT** for explicit user confirmation before applying any applicability changes
   
   This ensures traceability and prevents unintended reclassifications.

2. **Compelling reasons for applicability changes:** Only propose a change when there is clear evidence:
   - FLS demonstrates that Rust's type system or borrow checker prevents the issue entirely (→ `rust_prevents`)
   - The C/C++ concept has no meaningful Rust equivalent (→ `not_applicable`)
   - The MISRA ADD-6 classification appears incorrect based on FLS analysis
   - A `direct` mapping is more accurately characterized as `partial` due to Rust handling it differently

3. **Trust MISRA ADD-6 classifications:** When MISRA ADD-6 marks a guideline as `n_a`, keep it as `not_applicable` unless there's a compelling reason to reclassify. Focus verification on adding FLS justification and setting confidence to `high`.

4. **Always provide FLS justification:** Even when a MISRA rule is marked `n_a` (not applicable) or uses `no_equivalent` rationale, include FLS matches that **explain why** the concept doesn't apply to Rust. The `record-decision` tool will error if no matches are provided.

   **Exceptional cases:** Use `--force-no-matches` only when:
   - The MISRA rule is entirely about C preprocessor behavior with no Rust equivalent
   - The rule concerns C-specific syntax that has no parallel in Rust's grammar
   - Multiple thorough searches (`search-fls-deep`, `search-fls` with various queries) yielded nothing relevant
   
   When using `--force-no-matches`, the `--notes` field must document:
   - What searches were attempted
   - Why no FLS content is relevant
   - Why this is truly an exceptional case

5. **Confidence updates are always okay:** Changing from `medium` to `high` confidence is the expected outcome of verification.

6. **Applicability change report format:** At session end, after processing all guidelines, if any applicability changes are proposed, output a report:
   
   ```
   ## Proposed Applicability Changes
   
   | Guideline | Field | Current | Proposed | Rationale |
   |-----------|-------|---------|----------|-----------|
   | Rule X.Y  | applicability_all_rust | direct | rust_prevents | [brief reason] |
   ```
   
   After user approval, apply the changes in a separate update pass.

#### FLS ID Validation

The `record-decision` tool validates all FLS IDs against a pre-generated list of known valid IDs from the FLS specification. This prevents hallucinated or mistyped FLS IDs from being recorded.

**Validation behavior:**
- Invalid FLS IDs cause a hard error with guidance on how to find valid IDs
- If `valid_fls_ids.json` is missing, validation is skipped with a warning

**Refreshing the valid IDs:**
```bash
uv run generate-valid-fls-ids
```

This is also automatically called at the end of `extract-fls-content`, so the list stays current when FLS content is re-extracted.

**Sources combined for valid IDs:**
- `tools/data/fls_section_mapping.json` - Canonical section hierarchy
- `tools/data/synthetic_fls_ids.json` - Generated/fabricated IDs
- `embeddings/fls/chapter_*.json` - All paragraph-level IDs from extraction

### Applicability Values

**v2 uses simplified `applicability` values per context:**

| Value | Description |
|-------|-------------|
| `yes` | Guideline applies in this context |
| `no` | Guideline does not apply in this context |
| `partial` | Some aspects of the guideline apply |

**v2 `adjusted_category` values (per MISRA ADD-6):**

| Value | Description |
|-------|-------------|
| `required` | Required guideline (must comply) |
| `advisory` | Advisory guideline (should comply) |
| `recommended` | Recommended practice |
| `disapplied` | Guideline explicitly disapplied for Rust |
| `implicit` | Rust's design implicitly enforces this |
| `n_a` | Not applicable to Rust |

**v1 legacy values (for reference):**

| Value | Description |
|-------|-------------|
| `direct` | Maps directly to FLS concept(s) |
| `partial` | Concept exists but Rust handles differently |
| `not_applicable` | C/C++ specific, no Rust equivalent |
| `rust_prevents` | Rust's design prevents the issue entirely |
| `unmapped` | Awaiting expert mapping |

### FLS Rationale Types

#### Definitions and Decision Criteria

| Type | Definition | Test Question | Coding Guideline Implication |
|------|------------|---------------|------------------------------|
| `direct_mapping` | MISRA rule maps directly to FLS concepts | "Does Rust have equivalent rules/constraints?" | **Adapt** MISRA rule for Rust |
| `partial_mapping` | Some aspects map, others don't | "Does only part of the rule apply?" | **Partial adaptation** needed |
| `rust_alternative` | Rust has a different mechanism for the same goal | "Does Rust solve this problem differently?" | Consider **separate** Rust-specific guidelines |
| `rust_prevents` | Rust's design makes the issue impossible | "Does Rust's type system/borrow checker prevent this?" | **Verify** prevention is complete; check escape hatches |
| `no_equivalent` | The C concept doesn't exist in Rust | "Does the C concept literally not exist?" | **None** needed - document as N/A |

#### Distinguishing `no_equivalent` from `rust_alternative`

This is the most common point of confusion. Use this test:

| Question | `no_equivalent` | `rust_alternative` |
|----------|-----------------|-------------------|
| Does the underlying safety concern exist? | No - the problem space doesn't exist | Yes - but Rust solves it differently |
| Is there a Rust mechanism addressing it? | No mechanism needed | Yes - a different mechanism |

#### Concrete Examples

**`no_equivalent` - Dir 4.10 (Header Guards):**
- C problem: Headers can be included multiple times, causing redefinition errors
- Rust: No header files exist. Modules are compiled once by design.
- Classification: `no_equivalent` - the problem space (textual inclusion) doesn't exist
- `accepted_matches`: Modules, Use Imports, Source Files (explain WHY no headers)

**`rust_alternative` - Dir 4.8 (Opaque Pointers):**
- C problem: Hide implementation details from external code
- Rust: Uses visibility system (`pub`, `pub(crate)`, private-by-default) instead
- Classification: `rust_alternative` - same goal (encapsulation), different mechanism
- `accepted_matches`: Visibility, Struct Types, Field Access (show HOW Rust does it)

**`rust_prevents` - Rule 10.4 (Usual Arithmetic Conversions):**
- C problem: Implicit type promotions in arithmetic can cause unexpected results
- Rust: Type system requires operands to be the same type; `i32 + i64` is a compile error
- Classification: `rust_prevents` - Rust's type system makes the issue impossible
- `accepted_matches`: Arithmetic Expressions, Type Coercion (show HOW Rust prevents it)
- Note: `as` casts are an escape hatch that may need separate guidelines

### Validation

```bash
cd tools
uv run validate-standards
uv run validate-synthetic-ids
```

### map-misra-to-fls CLI Options

Used for initial mapping generation (Pipeline 2). Not typically needed during verification.

| Option | Default | Description |
|--------|---------|-------------|
| `--section-threshold` | 0.5 | Minimum section similarity score |
| `--paragraph-threshold` | 0.55 | Minimum paragraph similarity score |
| `--max-section-matches` | 5 | Max section matches per guideline |
| `--max-paragraph-matches` | 10 | Max paragraph matches per guideline |
| `--no-similarity` | - | Use legacy keyword matching (not recommended) |
| `--no-preserve` | - | Overwrite existing high-confidence entries |
| `--verbose` | - | Print detailed matching info |

### Verification Progress Tracking

Progress is tracked in `coding-standards-fls-mapping/verification_progress.json` to enable:
- Resuming verification across sessions
- Batch-based organization of work
- Session history for auditing

Schema: `coding-standards-fls-mapping/schema/verification_progress.schema.json`

#### Batch Structure

| Batch | Name | Criteria |
|-------|------|----------|
| 1 | High-score direct | Existing high-confidence + `direct` with max score ≥0.65 |
| 2 | Not applicable | `applicability_all_rust: not_applicable` (still require FLS justification) |
| 3 | Stdlib & Resources | Categories 21+22 remaining `direct` guidelines |
| 4 | Medium-score direct | Remaining `direct` with score 0.5-0.65 |
| 5 | Edge cases | `partial`, `rust_prevents`, and any remaining |

#### Generating/Updating Progress File

```bash
cd tools

# Initial creation
uv run scaffold-progress --standard misra-c

# Preview batch assignments without writing
uv run scaffold-progress --standard misra-c --dry-run

# Regenerate from scratch (loses progress)
uv run scaffold-progress --standard misra-c --force

# Regenerate batches but preserve completed work
uv run scaffold-progress --standard misra-c --preserve-completed
```

#### Resetting a Batch

To reset verification decisions for a batch (e.g., to re-verify after issues):

```bash
cd tools

# Reset all guidelines in a batch to unverified state (both contexts)
uv run reset-batch --standard misra-c --batch 3

# Reset only all_rust context in batch 3
uv run reset-batch --standard misra-c --batch 3 --context all_rust

# Reset only safe_rust context in batch 3
uv run reset-batch --standard misra-c --batch 3 --context safe_rust

# Reset specific guidelines within a batch
uv run reset-batch --standard misra-c --batch 3 --guidelines "Rule 22.1,Rule 22.2"

# Preview what would be reset without making changes
uv run reset-batch --standard misra-c --batch 3 --dry-run

# Reset ALL verification state for complete re-verification
uv run reset-verification --standard misra-c
```

**v2 context reset:** The `--context` flag allows selective reset of only one context while preserving the other. This is useful when re-verifying decisions for one context without losing work on the other.

This clears `verification_decision` fields in the batch report and resets `verified` status in `verification_progress.json` for affected guidelines and contexts.

---

## Development Guidelines

### Tool Development with uv

All tools are developed as entry points in the `fls-tools` package. When creating new tools:

1. **Create the module** in the appropriate location under `tools/src/fls_tools/`:
   - `iceoryx2/` - Pipeline 1 tools
   - `standards/verification/` - Verification workflow tools
   - `standards/validation/` - Validation tools
   - `standards/mapping/` - Mapping generation tools
   - `analysis/` - Cross-reference and analysis tools

2. **Add entry point** in `tools/pyproject.toml` under `[project.scripts]`:
   ```toml
   tool-name = "fls_tools.module.submodule:main"
   ```

3. **Follow existing patterns:**
   - Import shared utilities from `fls_tools.shared`
   - Use `argparse` for CLI arguments
   - Use `get_project_root()` for path resolution
   - Include docstring with usage examples

4. **Test the tool:**
   ```bash
   cd tools
   uv run tool-name --help
   uv run tool-name --dry-run  # If applicable
   ```

### Ad-Hoc Scripts Policy

Ad-hoc Python/Bash scripts (not registered as tools) follow these rules:

**Acceptable for READ-ONLY operations:**
- Analysis and reporting
- Data extraction and inspection
- One-off queries against data files
- Generating summaries or statistics

**Require explicit user approval for:**
- Any modification to canonical data files
- Batch updates to JSON files
- Operations that bypass validation tooling

**NOT acceptable (use proper tooling instead):**
- Operations that have a dedicated tool/command
- Modifications that should be auditable/traceable
- Recurring operations that should be reproducible

**When proposing an ad-hoc modification script:**
1. Explain the rationale and what it will change
2. Ask for explicit approval before executing
3. Consider whether the operation should become a reusable tool

---

## References

- [Ferrocene Language Specification](https://rust-lang.github.io/fls/)
- [iceoryx2 Repository](https://github.com/eclipse-iceoryx/iceoryx2)
- [MISRA C:2025](https://misra.org.uk/)
- [SEI CERT C](https://wiki.sei.cmu.edu/confluence/display/c/)
