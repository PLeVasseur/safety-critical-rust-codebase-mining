# FLS Mapping Agent Guide

This document describes the tools, workflows, and data structures for two related mapping efforts:

1. **iceoryx2 FLS Mapping** - Document how iceoryx2 uses Rust language constructs per the Ferrocene Language Specification (FLS)
2. **Coding Standards Mapping** - Map MISRA/CERT safety guidelines to FLS sections using semantic similarity

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

| Command | Purpose | Usage |
|---------|---------|-------|
| `analyze-coverage` | Cross-reference FLS usage across all mappings | `uv run analyze-coverage` |
| `review-mappings` | Interactive/batch review of coding standard mappings | `uv run review-mappings --standard misra-c --interactive` |

**Future:** Pipeline 3 will cross-reference iceoryx2-FLS mappings with coding standards mappings to prioritize which coding guidelines to verify based on frequency of construct usage in iceoryx2.

### Shared Resources

| File | Location | Description |
|------|----------|-------------|
| `fls_section_mapping.json` | `tools/data/` | Canonical FLS section hierarchy with fabricated sections |
| `fls_id_to_section.json` | `tools/data/` | Reverse lookup from FLS ID to section |
| `synthetic_fls_ids.json` | `tools/data/` | Tracks generated FLS IDs |
| `concept_to_fls.json` | `coding-standards-fls-mapping/` | C concept to FLS ID keyword mappings |
| `misra_rust_applicability.json` | `coding-standards-fls-mapping/` | MISRA ADD-6 Rust applicability data |

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
│   ├── concept_to_fls.json             # C concept to FLS ID mappings
│   ├── misra_rust_applicability.json   # MISRA ADD-6 Rust applicability
│   └── verification_progress.json      # Verification batch tracking
│
├── embeddings/                         # Extracted content and embeddings
│   ├── fls/
│   │   ├── index.json                  # Chapter listing and statistics
│   │   ├── chapter_01.json             # Per-chapter extracted content
│   │   ├── ...
│   │   ├── chapter_22.json
│   │   ├── embeddings.pkl              # FLS section-level embeddings (338)
│   │   └── paragraph_embeddings.pkl    # FLS paragraph-level embeddings (3,733)
│   ├── misra_c/
│   │   ├── embeddings.pkl              # MISRA C guideline-level embeddings
│   │   ├── query_embeddings.pkl        # MISRA C query-level embeddings
│   │   ├── rationale_embeddings.pkl    # MISRA C rationale embeddings
│   │   └── amplification_embeddings.pkl # MISRA C amplification embeddings
│   └── similarity/
│       └── misra_c_to_fls.json         # Similarity computation results
│
├── cache/                              # Cached data (gitignored)
│   ├── repos/
│   │   ├── iceoryx2/v0.8.0/            # iceoryx2 source at specific versions
│   │   └── fls/                        # FLS RST source files
│   ├── verification/                   # Batch verification reports
│   │   └── batch{N}_session{M}.json
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
    │   │       ├── progress.py         # check-progress
    │   │       ├── reset.py            # reset-batch
    │   │       ├── scaffold.py         # scaffold-progress
    │   │       ├── search.py           # search-fls
    │   │       ├── search_deep.py      # search-fls-deep
    │   │       └── recompute.py        # recompute-similarity
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
> 
> These files are gitignored and must NEVER be committed. Batch reports should be deleted immediately after successful application via `apply-verification`.

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
**mappings/*.json** - FLS mappings with `accepted_matches`:

```json
{
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  "applicability_all_rust": "direct",
  "applicability_safe_rust": "not_applicable",
  "accepted_matches": [
    {
      "fls_id": "fls_xxx",
      "category": 0,
      "fls_title": "Type Cast Expressions",
      "score": 0.65,
      "reason": "Per FLS: 'A cast is legal when...' This directly addresses MISRA's concern."
    }
  ],
  "rejected_matches": [
    {
      "fls_id": "fls_yyy",
      "category": 0,
      "score": 0.62,
      "reason": "Section is about enum layout, not type conversions."
    }
  ],
  "fls_rationale_type": "direct_mapping",
  "confidence": "high"
}
```

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

#### Phase 0: Check Progress

Before starting, run `check-progress` to determine current state:

```bash
cd tools
uv run check-progress
```

This shows:
- Last session ID and next session ID to use
- Current batch and its status
- Whether a batch report exists in `cache/verification/`
- If resuming, which guideline to continue from
- Suggested command for Phase 1 (if batch report doesn't exist)

**Crash recovery:** If a session was interrupted, `check-progress` will detect an existing batch report with partial work and indicate where to resume.

#### Phase 1: Data Gathering

If no batch report exists, run `verify-batch` to generate one:

```bash
cd tools
uv run verify-batch \
    --batch BATCH_ID \
    --session SESSION_ID \
    --mode llm \
    --output ../cache/verification/batchBATCH_ID_sessionSESSION_ID.json
```

**What it extracts:**
- Similarity matches (section and paragraph) above thresholds
- MISRA rationale from extracted text
- Wide-shot FLS content (matched sections + siblings + all rubrics)
- Current mapping state

All guidelines start with a scaffolded `verification_decision` structure (fields set to `null`/empty).
See `coding-standards-fls-mapping/schema/batch_report.schema.json` for required fields.

**Output modes:**
- `--mode llm`: Full JSON optimized for LLM consumption
- `--mode human`: Markdown summary for quick review

**Thresholds** (configurable via CLI):

| Option | Default | Description |
|--------|---------|-------------|
| `--section-threshold` | 0.5 | Minimum section similarity score |
| `--paragraph-threshold` | 0.55 | Minimum paragraph similarity score |

**Failure conditions:** Script fails immediately if `cache/misra_c_extracted_text.json` is missing.

#### Phase 2: Analysis & Decision (LLM)

If resuming an interrupted session, output "Resuming from Rule X.Y (N/M complete)" at the start.

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

3. **Search FLS for relevant content:**

   Use at least one of these search tools as part of analysis, and additional methods as needed:

   ```bash
   # Semantic search across all FLS content
   uv run search-fls --query "memory allocation" --top 10

   # Deep search using all MISRA embedding types for a guideline
   uv run search-fls-deep --guideline "Rule 21.3"

   # Recompute similarity for specific guideline
   uv run recompute-similarity --guideline "Rule 21.3"
   ```

   **Guidelines for search tools** (use discretion):

   | Condition | Consider Using |
   |-----------|----------------|
   | Quick concept lookup (e.g., "pointer arithmetic") | `search-fls` |
   | Exploring tangential concepts not in MISRA text | `search-fls` |
   | Batch report shows no/few matches but MISRA rationale is substantive | `search-fls-deep` or `recompute-similarity` |
   | Pre-computed similarity seems to have missed obvious FLS sections | `recompute-similarity` |

   **Additional methods** if search tools are not sufficient:
   - Read FLS chapter files directly (`embeddings/fls/chapter_NN.json`)
   - Grep across FLS content for keywords
   - Check `tools/data/fls_section_mapping.json` for section hierarchy
   - Check `coding-standards-fls-mapping/concept_to_fls.json` for known concept mappings

4. **Make decisions:**
   - Accept matches with score and detailed reason (quote FLS paragraphs)
   - Reject matches above threshold with explanation
   - **May propose FLS sections not in similarity results** - clearly document why in the `reason` field

5. **Flag applicability changes** (do not apply yet):
   
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

6. **Populate** the `verification_decision` section in batch report JSON

   **Required fields** (see `coding-standards-fls-mapping/schema/batch_report.schema.json`):
   - `decision`: "accept_with_modifications", "accept_no_matches", "accept_existing", or "reject"
   - `confidence`: "high", "medium", or "low"
   - `fls_rationale_type`: "direct_mapping", "rust_alternative", "rust_prevents", "no_equivalent", or "partial_mapping"
   - `accepted_matches`: Array of FLS matches (each with `fls_id`, `category`, `score`, `reason`)
   - `rejected_matches`: Array of explicitly rejected matches (optional)
   - `notes`: Additional notes (optional)

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
    --batch-report ../cache/verification/batchBATCH_ID_sessionSESSION_ID.json \
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
   uv run check-progress
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
   
   Batch reports contain copyrighted MISRA rationale text extracted from the MISRA PDF and must not be retained after verification is complete.
   
   Prompt the user:
   > "The batch report `cache/verification/batch3_session5.json` contains copyrighted MISRA text. Shall I delete it?"
   
   **Wait for explicit user approval before deleting.**

5. **Upon approval, delete the batch report:**
   ```bash
   rm cache/verification/batchN_sessionM.json
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

4. **Confidence updates are always okay:** Changing from `medium` to `high` confidence is the expected outcome of verification.

5. **Applicability change report format:** At session end, after processing all guidelines, if any applicability changes are proposed, output a report:
   
   ```
   ## Proposed Applicability Changes
   
   | Guideline | Field | Current | Proposed | Rationale |
   |-----------|-------|---------|----------|-----------|
   | Rule X.Y  | applicability_all_rust | direct | rust_prevents | [brief reason] |
   ```
   
   After user approval, apply the changes in a separate update pass.

### Applicability Values

| Value | Description |
|-------|-------------|
| `direct` | Maps directly to FLS concept(s) |
| `partial` | Concept exists but Rust handles differently |
| `not_applicable` | C/C++ specific, no Rust equivalent |
| `rust_prevents` | Rust's design prevents the issue entirely |
| `unmapped` | Awaiting expert mapping |

### FLS Rationale Types

| Value | Description |
|-------|-------------|
| `direct_mapping` | Rule maps directly to FLS concepts |
| `rust_alternative` | Rust has a different/better mechanism |
| `rust_prevents` | Rust's design prevents the issue |
| `no_equivalent` | C concept doesn't exist in Rust |
| `partial_mapping` | Some aspects map, others don't |

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
uv run scaffold-progress

# Preview batch assignments without writing
uv run scaffold-progress --dry-run

# Regenerate from scratch (loses progress)
uv run scaffold-progress --force

# Regenerate batches but preserve completed work
uv run scaffold-progress --preserve-completed
```

#### Resetting a Batch

To reset verification decisions for a batch (e.g., to re-verify after issues):

```bash
cd tools

# Reset all guidelines in a batch to unverified state
uv run reset-batch --batch 3

# Reset specific guidelines within a batch
uv run reset-batch --batch 3 --guidelines "Rule 22.1,Rule 22.2"

# Preview what would be reset without making changes
uv run reset-batch --batch 3 --dry-run
```

This clears `verification_decision` fields in the batch report and resets `verified` status in `verification_progress.json` for affected guidelines.

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
