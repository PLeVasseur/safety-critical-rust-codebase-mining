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

| Script | Input | Output | Description |
|--------|-------|--------|-------------|
| `clone_iceoryx2.py` | GitHub | `cache/repos/iceoryx2/v{VERSION}/` | Clone iceoryx2 at specific version tags |
| `extract_fls_sections.py` | FLS RST files | `fls_section_mapping.json` | Extract FLS section hierarchy |
| `restructure_fls_json.py` | `fls_section_mapping.json` | `iceoryx2-fls-mapping/*.json` | Generate chapter JSON skeletons |
| `normalize_fls_json.py` | Chapter JSON files | Normalized chapter JSON | Normalize field names and structure |
| `update_fls_counts_samples.py` | iceoryx2 source + chapter JSON | Updated chapter JSON | Add counts and code samples |
| `validate_fls_json.py` | `iceoryx2-fls-mapping/*.json` | Validation report | Schema, coverage, sample validation |

**Run Pipeline 1:**
```bash
cd tools
uv run python clone_iceoryx2.py --from 0.7.0 --to 0.8.0
uv run python extract_fls_sections.py
uv run python normalize_fls_json.py
uv run python update_fls_counts_samples.py
uv run python validate_fls_json.py
```

### Pipeline 2: Coding Standards Mapping

Maps MISRA C/C++ and CERT C/C++ guidelines to FLS sections using semantic similarity.

**Standards Extraction:**

| Script | Input | Output | Description |
|--------|-------|--------|-------------|
| `extract_misra_rules.py` | MISRA PDF | `standards/misra_c_2025.json` | Extract MISRA rule listings |
| `scrape_cert_rules.py` | CERT Wiki | `standards/cert_*.json` | Scrape CERT rule listings |

**Embedding Pipeline (in `tools/embeddings/`):**

| Script | Input | Output | Description |
|--------|-------|--------|-------------|
| `extract_fls_content.py` | FLS RST files | `embeddings/fls/chapter_NN.json`, `index.json` | Extract FLS with rubric-categorized paragraphs |
| `extract_misra_text.py` | MISRA PDF | `cache/misra_c_extracted_text.json` | Extract MISRA guideline full text |
| `generate_embeddings.py` | Extracted JSON files | `embeddings.pkl`, `paragraph_embeddings.pkl` | Generate section (338) and paragraph (3,733) embeddings |
| `compute_similarity.py` | Embedding files | `embeddings/similarity/misra_c_to_fls.json` | Compute cosine similarity matrix |
| `orchestrate.py` | (runs above) | All outputs | Convenience script for full pipeline |

**Mapping Generation:**

| Script | Input | Output | Description |
|--------|-------|--------|-------------|
| `sync_fls_section_mapping.py` | `embeddings/fls/chapter_NN.json` | Updated `fls_section_mapping.json` | Generate fabricated section entries |
| `map_misra_to_fls.py` | Similarity + concepts | `mappings/misra_c_to_fls.json` | Generate automated mappings |

**Run Pipeline 2:**
```bash
cd tools
# Option A: Use orchestrator
uv run python embeddings/orchestrate.py --force

# Option B: Run steps manually
uv run python embeddings/extract_fls_content.py
uv run python sync_fls_section_mapping.py
uv run python embeddings/generate_embeddings.py
uv run python embeddings/compute_similarity.py
uv run python map_misra_to_fls.py

# Validate
uv run python validate_coding_standards.py
uv run python validate_synthetic_ids.py
```

### Pipeline 3: Cross-Reference & Analysis

| Script | Purpose | Usage |
|--------|---------|-------|
| `analyze_fls_coverage.py` | Cross-reference FLS usage across all mappings | `uv run python analyze_fls_coverage.py` |
| `review_fls_mappings.py` | Interactive/batch review of coding standard mappings | `uv run python review_fls_mappings.py --standard misra-c --interactive` |

**Future:** Pipeline 3 will cross-reference iceoryx2-FLS mappings with coding standards mappings to prioritize which coding guidelines to verify based on frequency of construct usage in iceoryx2.

### Shared Resources

| File | Used By | Description |
|------|---------|-------------|
| `fls_section_mapping.json` | Most scripts | Canonical FLS section hierarchy with fabricated sections |
| `concept_to_fls.json` | `map_misra_to_fls.py` | C concept to FLS ID keyword mappings |
| `misra_rust_applicability.json` | `map_misra_to_fls.py` | MISRA ADD-6 Rust applicability data |
| `synthetic_fls_ids.json` | `validate_synthetic_ids.py` | Tracks generated FLS IDs |

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
│   │   ├── coding_standard_rules.schema.json
│   │   └── fls_mapping.schema.json
│   ├── standards/                      # Extracted rule listings
│   │   ├── misra_c_2025.json
│   │   ├── misra_cpp_2023.json
│   │   ├── cert_c.json
│   │   └── cert_cpp.json
│   └── mappings/                       # FLS mappings (deliverables)
│       ├── misra_c_to_fls.json
│       ├── misra_cpp_to_fls.json
│       ├── cert_c_to_fls.json
│       └── cert_cpp_to_fls.json
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
│   │   └── embeddings.pkl              # MISRA C vector embeddings
│   └── similarity/
│       └── misra_c_to_fls.json         # Similarity computation results
│
├── cache/                              # Cached source repositories (gitignored)
│   ├── repos/
│   │   ├── iceoryx2/v0.8.0/            # iceoryx2 source at specific versions
│   │   └── fls/                        # FLS RST source files
│   └── misra_c_extracted_text.json     # Extracted MISRA text (gitignored)
│
└── tools/                              # All scripts
    ├── embeddings/                     # Embedding pipeline scripts
    │   ├── extract_fls_content.py
    │   ├── extract_misra_text.py
    │   ├── generate_embeddings.py
    │   ├── compute_similarity.py
    │   └── orchestrate.py
    ├── clone_iceoryx2.py
    ├── extract_fls_sections.py
    ├── extract_misra_rules.py
    ├── scrape_cert_rules.py
    ├── map_misra_to_fls.py
    ├── sync_fls_section_mapping.py
    ├── normalize_fls_json.py
    ├── restructure_fls_json.py
    ├── update_fls_counts_samples.py
    ├── analyze_fls_coverage.py
    ├── review_fls_mappings.py
    ├── validate_fls_json.py
    ├── validate_coding_standards.py
    ├── validate_synthetic_ids.py
    ├── fls_section_mapping.json        # Canonical FLS section hierarchy
    ├── concept_to_fls.json
    ├── misra_rust_applicability.json
    └── synthetic_fls_ids.json
```

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
uv run python clone_iceoryx2.py --from 0.8.0 --to 0.9.0
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
uv run python validate_fls_json.py
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
uv run python validate_fls_json.py                    # All checks
uv run python validate_fls_json.py --file=fls_chapter15_ownership_destruction.json
uv run python validate_fls_json.py --audit-samples    # Sample quality audit
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

For each MISRA guideline requiring manual verification, follow these steps rigorously:

#### Step 1: Get Similarity Results

```bash
cd tools && uv run python -c "
import json
with open('../embeddings/similarity/misra_c_to_fls.json') as f:
    sim = json.load(f)
rule = 'Rule X.Y'  # Replace with actual rule

print('=== Section Matches ===')
for m in sim['results'][rule]['top_matches'][:5]:
    print(f'{m[\"fls_id\"]}: {m[\"similarity\"]:.3f} - {m[\"title\"]}')

print('\\n=== Paragraph Matches ===')
for m in sim['results'][rule]['top_paragraph_matches'][:5]:
    print(f'{m[\"fls_id\"]}: {m[\"similarity\"]:.3f} [{m[\"category_name\"]}] {m[\"text_preview\"][:60]}...')
"
```

#### Step 2: Evaluate Similarity Quality

**Section Matches (threshold: 0.5):**

| Score | Interpretation | Action |
|-------|----------------|--------|
| **>=0.6** | Strong match | MUST investigate. Document if rejected. |
| **0.5-0.6** | Medium match | Investigate and document decision |

**Paragraph Matches (threshold: 0.55):**

| Score | Interpretation | Action |
|-------|----------------|--------|
| **>=0.65** | Strong match | Quote this paragraph in reason field |
| **0.55-0.65** | Medium match | Investigate the parent section |

All matches above threshold that are NOT accepted MUST be added to `rejected_matches` with explanation.

#### Understanding Match Types

The similarity results contain two types of matches:

1. **Section matches (`top_matches`)**: Match against cleaned section-level content (338 sections). Identify which FLS topics are relevant.

2. **Paragraph matches (`top_paragraph_matches`)**: Match against individual rubric paragraphs (3,733 paragraphs). Provide specific quotable evidence.

**Paragraph match fields:**

| Field | Description |
|-------|-------------|
| `fls_id` | Paragraph's FLS ID (use in `reason` for quotes) |
| `section_fls_id` | Parent section's FLS ID |
| `section_title` | Parent section title |
| `category` | -2=legality_rules, -3=dynamic_semantics, -4=undefined_behavior, etc. |
| `category_name` | Human-readable category name |
| `text_preview` | First 200 chars of paragraph text |

**Best practice:** Use paragraph matches to find quotable evidence, then include the paragraph's `fls_id` directly in `accepted_matches`.

#### Step 3: Read FLS Content

Look up the FLS section content:

```python
import json
with open('embeddings/fls/chapter_15.json') as f:
    chapter = json.load(f)

section = next(s for s in chapter['sections'] if s['fls_id'] == 'fls_xxx')

# Focus on legality rules (-2) and UB (-4)
for cat in ['-2', '-4']:
    for pid, text in section['rubrics'].get(cat, {}).get('paragraphs', {}).items():
        print(f"[{cat}] {pid}: {text}")
```

Focus on:
- Legality rules (what the compiler enforces)
- Undefined behavior definitions
- Dynamic semantics (runtime behavior)

#### Step 4: Compare MISRA Rationale to FLS

```bash
cd tools && uv run python -c "
import json
with open('../cache/misra_c_extracted_text.json') as f:
    misra = json.load(f)
for g in misra['guidelines']:
    if g['guideline_id'] == 'Rule X.Y':
        print(g['rationale'])
"
```

Ask:
- Does the FLS section actually address the MISRA concern?
- Is Rust's approach the same, different, or does it prevent the issue?
- Are multiple FLS sections needed together?

#### Step 5: Make Mapping Decision

1. **Accept similarity suggestion:** Add to `accepted_matches` with score and reason quoting specific FLS paragraphs
2. **Override with different FLS IDs:** Add rejected matches (>=0.5) to `rejected_matches` with explanation
3. **No FLS mapping needed:** Set `accepted_matches` to empty array with explanation

#### Step 6: Update Mapping with Evidence

```json
{
  "guideline_id": "Rule X.Y",
  "accepted_matches": [
    {
      "fls_id": "fls_xxx",
      "category": -2,
      "fls_section": "15.2",
      "fls_title": "References",
      "score": 0.65,
      "reason": "Per FLS fls_ev4a82fdhwr8: 'A reference shall point to an initialized referent.' This directly addresses MISRA's concern about..."
    }
  ],
  "rejected_matches": [
    {
      "fls_id": "fls_yyy",
      "category": 0,
      "fls_section": "15.3",
      "score": 0.62,
      "reason": "Section is about X, not Y - semantic similarity due to shared terminology"
    }
  ],
  "confidence": "high",
  "notes": "High-level summary: Rust's borrow checker prevents the uninitialized access that MISRA is trying to prevent."
}
```

#### Verification Guidelines

1. **Reclassification requires approval:** If analysis suggests changing `applicability_all_rust`, `applicability_safe_rust`, or `fls_rationale_type` from existing values, check with the user before making the change.

2. **Trust MISRA ADD-6 classifications:** When MISRA ADD-6 marks a guideline as `n_a`, keep it as `not_applicable` unless there's a compelling reason to reclassify. Focus verification on adding FLS justification and setting confidence to `high`.

3. **Confidence updates are always okay:** Changing from `medium` to `high` confidence is the expected outcome of verification.

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
uv run python validate_coding_standards.py
uv run python validate_synthetic_ids.py
```

### map_misra_to_fls.py CLI Options

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

#### Generating/Updating Progress File

```bash
cd tools

# Initial creation
uv run python scaffold_verification_progress.py

# Preview batch assignments without writing
uv run python scaffold_verification_progress.py --dry-run

# Regenerate from scratch (loses progress)
uv run python scaffold_verification_progress.py --force

# Regenerate batches but preserve completed work
uv run python scaffold_verification_progress.py --preserve-completed
```

#### Batch Structure

| Batch | Name | Criteria |
|-------|------|----------|
| 1 | High-score direct | Existing high-confidence + `direct` with max score ≥0.65 |
| 2 | Not applicable | `applicability_all_rust: not_applicable` (still require FLS justification) |
| 3 | Stdlib & Resources | Categories 21+22 remaining `direct` guidelines |
| 4 | Medium-score direct | Remaining `direct` with score 0.5-0.65 |
| 5 | Edge cases | `partial`, `rust_prevents`, and any remaining |

#### Per-Guideline Workflow

For each guideline:

1. Get similarity results (section + paragraph matches)
2. Read FLS content (legality rules, UB, dynamic semantics)
3. Read MISRA rationale from extracted text
4. Present analysis with accept/reject decisions
5. Update `misra_c_to_fls.json` (set `confidence: "high"`)
6. Update `verification_progress.json` (mark guideline as `verified`, record `session_id`)

#### Validation Checkpoints

Run every 5-10 guidelines:

```bash
cd tools
uv run python validate_coding_standards.py
uv run python validate_synthetic_ids.py
```

#### Resuming Across Sessions

1. Read `verification_progress.json` to find current batch and next pending guideline
2. Create new session entry with incremented `session_id`
3. Continue per-guideline workflow
4. Update progress file after each guideline
5. Run validation checkpoints periodically

---

## References

- [Ferrocene Language Specification](https://rust-lang.github.io/fls/)
- [iceoryx2 Repository](https://github.com/eclipse-iceoryx/iceoryx2)
- [MISRA C:2025](https://misra.org.uk/)
- [SEI CERT C](https://wiki.sei.cmu.edu/confluence/display/c/)
