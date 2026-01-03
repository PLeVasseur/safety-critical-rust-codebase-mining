# Rust Context Search Infrastructure

**Status:** In Progress  
**Created:** 2026-01-03  
**Last Updated:** 2026-01-03

## Overview

This document describes the plan to add Rust-specific documentation sources to the verification workflow. The goal is to provide richer context when mapping MISRA C guidelines to Rust, helping determine whether:

- Rust has the same problem (→ `direct_mapping`)
- Rust solves it differently (→ `rust_alternative`)
- Rust's design prevents it (→ `rust_prevents`)
- The concept doesn't exist in Rust (→ `no_equivalent`)

## Motivation

Currently, the verification workflow searches the FLS directly using MISRA guideline text and manually-crafted queries. This can miss relevant context because:

1. MISRA uses C terminology that doesn't map directly to Rust concepts
2. The FLS is formal/normative but doesn't explain *why* Rust works the way it does
3. Unsafe Rust semantics are documented elsewhere (UCG, Nomicon)
4. Existing Rust tooling (Clippy) already addresses some MISRA-like concerns

By searching additional Rust documentation sources *before* the FLS, we can:
- Get better "steering" terms for FLS searches
- Find authoritative explanations of Rust mechanisms
- Identify existing tooling coverage
- Make more informed rationale type decisions

## Data Sources

| Source | Repository/URL | Focus | Priority |
|--------|---------------|-------|----------|
| **Rust Reference** | https://github.com/rust-lang/reference | Authoritative language reference (safe + unsafe) | 1 |
| **Unsafe Code Guidelines (UCG)** | https://github.com/rust-lang/unsafe-code-guidelines | Formal unsafe semantics | 2 |
| **Rustonomicon** | https://github.com/rust-lang/nomicon | Practical unsafe Rust guide | 3 |
| **Clippy Lints** | https://github.com/rust-lang/rust-clippy | ~700 lints with descriptions | 4 |

### Source Details

#### Rust Reference
- **Format:** mdBook (Markdown)
- **Structure:** `SUMMARY.md` defines hierarchy, `src/*.md` contains content
- **Value:** Covers all Rust language features, both safe and unsafe
- **Granularity:** Chapters → Sections → Paragraphs
- **ID Scheme:** `r[hierarchical.ids]` markers (e.g., `r[type.pointer.raw.safety]`)

#### Unsafe Code Guidelines (UCG)
- **Format:** mdBook (Markdown)
- **Structure:** Similar to Reference
- **Value:** Precise semantics for validity invariants, aliasing, layout, provenance
- **Granularity:** Chapters → Sections → Paragraphs
- **ID Scheme:** Standard markdown anchors (e.g., `[abi]: #abi-of-a-type`)

#### Rustonomicon
- **Format:** mdBook (Markdown)
- **Structure:** Similar to Reference
- **Value:** Practical guide with examples of safe unsafe patterns
- **Granularity:** Chapters → Sections → Paragraphs
- **ID Scheme:** None (headings only) - synthetic IDs generated during extraction

#### Clippy Lints
- **Format:** Rust source + rendered HTML docs
- **Structure:** Lint definitions in `clippy_lints/src/`, metadata extractable
- **Value:** Shows existing tooling coverage for safety concerns
- **Granularity:** Individual lints (name, category, description, example)
- **ID Scheme:** Lint names (e.g., `cast_ptr_alignment`)

**Clippy Categories:**
| Category | Description | Search Weight |
|----------|-------------|---------------|
| `correctness` | Code that is definitely wrong | 1.2x |
| `suspicious` | Code that is probably wrong | 1.15x |
| `complexity` | Code that is unnecessarily complex | 1.0x |
| `perf` | Performance improvements | 1.0x |
| `style` | Style/idiom improvements | 1.0x |
| `pedantic` | Very strict lints | 1.0x |
| `restriction` | Lints restricting certain patterns | 1.0x |
| `nursery` | Experimental lints | 0.9x |

### ID Scheme Comparison

| Source | ID Scheme | Example | Status |
|--------|-----------|---------|--------|
| **FLS** | `fls_xxxx` markers in RST | `fls_v5x85lt5ulva` | Native IDs |
| **Rust Reference** | `r[hierarchical.ids]` markers | `type.pointer.raw.safety` | Native IDs |
| **UCG** | Markdown anchors | `#abi-of-a-type` | Derived from anchors |
| **Nomicon** | None (headings only) | N/A | Synthetic IDs generated |
| **Clippy** | Lint names | `cast_ptr_alignment` | Native IDs |

**ID Integration Strategy:**

1. **FLS IDs** - Already tracked in `valid_fls_ids.json`, used in `record-decision --accept-match`
2. **Reference IDs** - Extract `r[...]` markers, create `valid_reference_ids.json`, optionally track in decisions
3. **UCG IDs** - Generate from markdown anchors (e.g., `ucg_glossary_abi`)
4. **Nomicon IDs** - Generate synthetic IDs from headings (e.g., `nomicon_transmutes`)
5. **Clippy IDs** - Use lint names directly (e.g., `clippy_cast_ptr_alignment`)

**Validation Files to Create:**
```
tools/data/
├── valid_fls_ids.json           # Existing
├── valid_reference_ids.json     # NEW: All r[...] IDs from Reference
├── reference_id_mapping.json    # NEW: ID -> section title/chapter mapping
```

**Cross-Reference in Decisions (Optional Enhancement):**

Reference IDs could be tracked alongside FLS IDs for richer documentation:
```bash
uv run record-decision \
    --accept-match "fls_abc123:Pointer Types:0:0.65:FLS states..." \
    --context-match "type.pointer.raw.safety:reference:Explains unsafe dereference requirement"
```

This would be informational (not required) since FLS is the normative source.

### Embedding Strategy

All sources are broken down to **paragraph-level** for fine-grained similarity search, mirroring the FLS approach.

**Context Prefix Pattern:**

Each paragraph's embedding text includes contextual prefixes to improve semantic matching:

| Source | Embedding Text Format | Example |
|--------|----------------------|---------|
| **FLS** | `Section: {title}\nCategory: {rubric}\n{text}` | `Section: Pointer Types\nCategory: Undefined Behavior\nIt is undefined behavior to dereference...` |
| **Reference** | `Chapter: {ch}\nSection: {sec}\n{text}` | `Chapter: Type system\nSection: Pointer types\nDereferencing a raw pointer is an unsafe operation.` |
| **UCG** | `Chapter: {ch}\nSection: {sec}\n{text}` | `Chapter: Glossary\nSection: Abstract Byte\nThe byte is the smallest unit of storage in Rust...` |
| **Nomicon** | `Chapter: {ch}\nSection: {sec}\n{text}` | `Chapter: Transmutes\nSection: Introduction\nGet out of our way type system!...` |
| **Clippy** | `Lint: {name}\nCategory: {cat}\n{desc}` | `Lint: cast_ptr_alignment\nCategory: correctness\nChecks for casts from a less-aligned pointer...` |

**Why Context Prefixes Help:**

1. **Semantic anchoring** - The embedding model understands "this is about pointer types" vs "this is about macros"
2. **Category awareness** - For FLS, knowing it's "Undefined Behavior" vs "Legality Rules" affects matching
3. **Cross-source consistency** - All sources use similar patterns, making similarity scores comparable

**Paragraph Granularity:**

| Source | Paragraph Definition |
|--------|---------------------|
| **FLS** | Content between `:dp:` markers within rubrics |
| **Reference** | Content between `r[...]` markers |
| **UCG** | Content between markdown anchors or headings |
| **Nomicon** | Content between headings (synthetic paragraph splits) |
| **Clippy** | Each lint is one "paragraph" (description + rationale combined) |

---

## Tool Architecture

All tools for this infrastructure live in a new package directory:

```
tools/src/fls_tools/rust_docs/
├── __init__.py
├── clone.py              # clone-rust-docs command
├── extract_reference.py  # extract-reference command
├── extract_ucg.py        # extract-ucg command
├── extract_nomicon.py    # extract-nomicon command
├── extract_clippy.py     # extract-clippy-lints command
├── generate.py           # generate-rust-embeddings command
├── search.py             # search-rust-context command
└── shared.py             # Shared mdBook parsing utilities
```

**Note:** The existing FLS clone tool (`clone-fls` in `fls_tools/iceoryx2/clone.py`) should be consolidated into this package as well, since it's also about cloning upstream Rust documentation.

### Entry Points (pyproject.toml)

```toml
[project.scripts]
# Rust docs infrastructure
clone-rust-docs = "fls_tools.rust_docs.clone:main"
extract-reference = "fls_tools.rust_docs.extract_reference:main"
extract-ucg = "fls_tools.rust_docs.extract_ucg:main"
extract-nomicon = "fls_tools.rust_docs.extract_nomicon:main"
extract-clippy-lints = "fls_tools.rust_docs.extract_clippy:main"
generate-rust-embeddings = "fls_tools.rust_docs.generate:main"
search-rust-context = "fls_tools.rust_docs.search:main"
```

### Shared Utilities (`shared.py`)

Common functionality for parsing mdBook sources:

```python
def parse_summary_md(path: Path) -> list[Chapter]:
    """Parse SUMMARY.md to get chapter/section hierarchy."""
    
def parse_mdbook_chapter(path: Path, chapter_info: Chapter) -> dict:
    """Parse a markdown chapter file into structured JSON."""
    
def extract_paragraphs(content: str) -> dict[str, str]:
    """Split content into paragraphs with generated IDs."""
    
def clean_markdown_for_embedding(text: str) -> str:
    """Remove code blocks, links, etc. for embedding generation."""
```

---

## Implementation Plan

### Phase 1: Repository Acquisition

**Goal:** Clone all 4 source repositories to a local cache.

**Output:**
```
cache/docs/
├── reference/                # rust-lang/reference
├── unsafe-code-guidelines/   # rust-lang/unsafe-code-guidelines
├── nomicon/                  # rust-lang/nomicon
└── rust-clippy/              # rust-lang/rust-clippy
```

**Tool:** `clone-rust-docs` (`tools/src/fls_tools/rust_docs/clone.py`)

```bash
uv run clone-rust-docs                     # Clone/update all sources
uv run clone-rust-docs --source reference  # Clone specific source
uv run clone-rust-docs --source all        # Explicit all
uv run clone-rust-docs --list              # List available sources and status
```

**Implementation Details:**

```python
RUST_DOC_SOURCES = {
    "reference": {
        "repo": "https://github.com/rust-lang/reference.git",
        "path": "reference",
        "description": "Rust Reference - authoritative language reference",
    },
    "ucg": {
        "repo": "https://github.com/rust-lang/unsafe-code-guidelines.git",
        "path": "unsafe-code-guidelines",
        "description": "Unsafe Code Guidelines - formal unsafe semantics",
    },
    "nomicon": {
        "repo": "https://github.com/rust-lang/nomicon.git",
        "path": "nomicon",
        "description": "Rustonomicon - practical unsafe Rust guide",
    },
    "clippy": {
        "repo": "https://github.com/rust-lang/rust-clippy.git",
        "path": "rust-clippy",
        "description": "Clippy - ~700 lints with descriptions",
    },
}
```

**Behavior:**
- Uses `--depth 1` for shallow clones (faster, smaller)
- If repo exists, does `git pull` to update
- Reports clone/update status for each source

**Status:** [x] Complete

**Subtasks:**
- [x] Create `tools/src/fls_tools/rust_docs/__init__.py`
- [x] Create `tools/src/fls_tools/rust_docs/clone.py`
- [x] Add entry point to `pyproject.toml`
- [x] Test cloning all sources

---

### Phase 2: Content Extraction - Rust Reference

**Goal:** Extract Reference content into structured JSON, preserving native `r[...]` IDs.

**Input:** `cache/docs/reference/src/` (mdBook markdown files)

**Output:**
```
embeddings/reference/
├── index.json                # Chapter/section listing with metadata
├── chapter_01.json           # Per-chapter content
├── chapter_02.json
├── ...

tools/data/
├── valid_reference_ids.json  # All extracted r[...] IDs for validation
├── reference_id_mapping.json # ID -> section title/chapter mapping
```

**JSON Structure:** Uses native `r[...]` IDs from source:
```json
{
  "source": "Rust Reference",
  "source_repo": "https://github.com/rust-lang/reference",
  "extraction_date": "2026-01-03",
  "chapter": 8,
  "title": "Type system",
  "sections": [
    {
      "id": "type.pointer",
      "title": "Pointer types",
      "level": 1,
      "content": "All pointers are explicit first-class values...",
      "parent_id": null,
      "paragraphs": {
        "type.pointer.intro": "All pointers are explicit first-class values...",
        "type.pointer.reference": "References (`&` and `&mut`)...",
        "type.pointer.reference.shared": "Shared references (`&`)...",
        "type.pointer.reference.shared.intro": "Shared references point to memory...",
        "type.pointer.raw": "Raw pointers (`*const` and `*mut`)...",
        "type.pointer.raw.safety": "Dereferencing a raw pointer is an unsafe operation."
      }
    }
  ]
}
```

**ID Extraction:**
- Parse `r[id.here]` markers from markdown files
- IDs are hierarchical (e.g., `type.pointer.raw.safety`)
- Store all valid IDs in `valid_reference_ids.json` for validation
- Create mapping from ID to section title/chapter for lookup

**Tool:** `extract-reference` (`tools/src/fls_tools/rust_docs/extract_reference.py`)

```bash
uv run extract-reference              # Extract all chapters
uv run extract-reference --chapter 6  # Extract specific chapter
uv run extract-reference --force      # Re-extract even if exists
```

**Status:** [ ] Not started

**Subtasks:**
- [ ] Create `tools/src/fls_tools/rust_docs/shared.py` with mdBook parsing utilities
- [ ] Create `tools/src/fls_tools/rust_docs/extract_reference.py`
- [ ] Implement `r[...]` ID extraction regex
- [ ] Generate `valid_reference_ids.json`
- [ ] Generate `reference_id_mapping.json`
- [ ] Add entry point to `pyproject.toml`
- [ ] Test extraction and validate JSON structure

---

### Phase 3: Content Extraction - UCG

**Goal:** Extract UCG content into structured JSON with anchor-derived IDs.

**Input:** `cache/docs/unsafe-code-guidelines/reference/src/` (mdBook markdown files)

**Output:**
```
embeddings/ucg/
├── index.json
├── chapter_01.json
├── ...
```

**ID Generation:** 
- Extract markdown anchor definitions (e.g., `[abi]: #abi-of-a-type`)
- Generate IDs in format `ucg_{anchor}` (e.g., `ucg_abi`)
- For sections without anchors, generate from heading (e.g., `ucg_glossary_abstract_byte`)

**Tool:** `extract-ucg` (`tools/src/fls_tools/rust_docs/extract_ucg.py`)

```bash
uv run extract-ucg
uv run extract-ucg --force
```

**Note:** UCG uses same mdBook structure as Reference but with markdown anchors instead of `r[...]` markers.

**Status:** [ ] Not started

**Subtasks:**
- [ ] Create `tools/src/fls_tools/rust_docs/extract_ucg.py`
- [ ] Implement markdown anchor extraction
- [ ] Add entry point to `pyproject.toml`
- [ ] Test extraction

---

### Phase 4: Content Extraction - Nomicon

**Goal:** Extract Nomicon content into structured JSON.

**Input:** `cache/docs/nomicon/src/` (mdBook markdown files)

**Output:**
```
embeddings/nomicon/
├── index.json
├── chapter_01.json
├── ...
```

**ID Generation:** Section IDs follow pattern `nomicon_{chapter}_{section}`.

**Tool:** `extract-nomicon` (`tools/src/fls_tools/rust_docs/extract_nomicon.py`)

```bash
uv run extract-nomicon
uv run extract-nomicon --force
```

**Note:** Nomicon uses same mdBook structure as Reference/UCG.

**Status:** [ ] Not started

**Subtasks:**
- [ ] Create `tools/src/fls_tools/rust_docs/extract_nomicon.py`
- [ ] Add entry point to `pyproject.toml`
- [ ] Test extraction

---

### Phase 5: Content Extraction - Clippy

**Goal:** Extract all ~700 Clippy lints with metadata.

**Input:** `cache/docs/rust-clippy/` (Rust source files + generated docs)

**Output:**
```
embeddings/clippy/
├── index.json                # Category listing and statistics
├── lints.json                # All lints with full descriptions
└── by_category/              # Lints grouped by category
    ├── correctness.json
    ├── suspicious.json
    ├── complexity.json
    ├── perf.json
    ├── style.json
    ├── pedantic.json
    ├── restriction.json
    └── nursery.json
```

**Lint JSON Structure (`lints.json`):**
```json
{
  "source": "Clippy",
  "source_repo": "https://github.com/rust-lang/rust-clippy",
  "extraction_date": "2026-01-03",
  "total_lints": 700,
  "lints": [
    {
      "id": "clippy_cast_ptr_alignment",
      "name": "cast_ptr_alignment",
      "category": "correctness",
      "level": "deny",
      "description": "Checks for casts from a less-aligned pointer to a more-aligned pointer",
      "rationale": "Dereferencing a misaligned pointer is undefined behavior...",
      "example_bad": "let ptr = &1u8 as *const u8 as *const u64;",
      "example_good": "// Use proper alignment or transmute with care",
      "applicability": "MachineApplicable",
      "search_weight": 1.2,
      "docs_url": "https://rust-lang.github.io/rust-clippy/master/#cast_ptr_alignment"
    }
  ]
}
```

**Extraction Approach:**
1. Parse `clippy_lints/src/declared_lints.rs` for lint list
2. For each lint, extract from its declaration file:
   - Name, category, level from `declare_clippy_lint!` macro
   - Description from doc comments
   - Examples from doc comments (if present)
3. Assign `search_weight` based on category:
   - `correctness`: 1.2
   - `suspicious`: 1.15
   - `nursery`: 0.9
   - All others: 1.0

**Tool:** `extract-clippy-lints` (`tools/src/fls_tools/rust_docs/extract_clippy.py`)

```bash
uv run extract-clippy-lints
uv run extract-clippy-lints --force
uv run extract-clippy-lints --category correctness  # Extract one category
```

**Status:** [ ] Not started

**Subtasks:**
- [ ] Create `tools/src/fls_tools/rust_docs/extract_clippy.py`
- [ ] Add entry point to `pyproject.toml`
- [ ] Test extraction with sample lints
- [ ] Verify all ~700 lints extracted

---

### Phase 6: Embedding Generation

**Goal:** Generate embeddings for all extracted content using the same model as FLS.

**Input:** Extracted JSON files from Phases 2-5

**Output:**
```
embeddings/reference/
├── embeddings.pkl            # Section-level embeddings
└── paragraph_embeddings.pkl  # Paragraph-level embeddings

embeddings/ucg/
├── embeddings.pkl
└── paragraph_embeddings.pkl

embeddings/nomicon/
├── embeddings.pkl
└── paragraph_embeddings.pkl

embeddings/clippy/
└── embeddings.pkl            # Lint-level embeddings (no paragraphs)
```

**Tool:** `generate-rust-embeddings` (`tools/src/fls_tools/rust_docs/generate.py`)

```bash
# Generate for specific source
uv run generate-rust-embeddings --source reference
uv run generate-rust-embeddings --source ucg
uv run generate-rust-embeddings --source nomicon
uv run generate-rust-embeddings --source clippy

# Generate for all sources
uv run generate-rust-embeddings --source all

# Force regeneration
uv run generate-rust-embeddings --source all --force
```

**Embedding Model:** 
- Must use same model as FLS embeddings for consistency
- Current FLS model: **TODO - verify from existing code**
- Document model name/version in output JSON

**Implementation Notes:**
- Reuse embedding generation logic from `tools/src/fls_tools/standards/embeddings/generate.py`
- For Clippy, embed the concatenation of `description` + `rationale`
- For mdBook sources, embed at both section and paragraph levels

**Status:** [ ] Not started

**Subtasks:**
- [ ] Verify current FLS embedding model
- [ ] Create `tools/src/fls_tools/rust_docs/generate.py`
- [ ] Add entry point to `pyproject.toml`
- [ ] Test embedding generation for each source
- [ ] Verify embedding dimensions match FLS

---

### Phase 7: Search Tool

**Goal:** Create unified search tool across all Rust documentation sources.

**Tool:** `search-rust-context` (`tools/src/fls_tools/rust_docs/search.py`)

```bash
# Search by MISRA guideline (uses guideline text as query)
uv run search-rust-context --guideline "Rule 11.3" --top 10

# Search by custom query
uv run search-rust-context --query "pointer aliasing alignment" --top 10

# Filter to specific sources
uv run search-rust-context --guideline "Rule 11.3" --sources ucg,nomicon

# Exclude Clippy
uv run search-rust-context --guideline "Rule 11.3" --no-clippy

# JSON output for programmatic use
uv run search-rust-context --guideline "Rule 11.3" --json
```

**Output Format (Human):**
```
============================================================
RUST CONTEXT SEARCH: Rule 11.3
============================================================
Guideline: A cast shall not be performed between a pointer to 
           object type and a pointer to a different object type

MISRA ADD-6 Context:
  Rationale: UB, DC
  All Rust: Yes (advisory)
  Safe Rust: No (n_a)

------------------------------------------------------------
RUST REFERENCE (3 matches)
------------------------------------------------------------
1. [0.74] Type Cast Expressions (ref_expressions_type_cast)
   "Casting between two integers of the same size is a no-op..."
   
2. [0.69] Pointer Types (ref_types_pointer)
   "Raw pointers *const T and *mut T..."

3. [0.62] Type Coercions (ref_type_coercions)
   "Coercions are implicit type conversions..."

------------------------------------------------------------
UNSAFE CODE GUIDELINES (2 matches)
------------------------------------------------------------
1. [0.72] Pointer Validity (ucg_glossary_pointer_validity)
   "A pointer is valid if it points to allocated memory..."

2. [0.68] Type Layout (ucg_layout_structs)
   "The layout of a type defines its size and alignment..."

------------------------------------------------------------
RUSTONOMICON (2 matches)
------------------------------------------------------------
1. [0.75] Casts (nomicon_casts)
   "The as keyword allows explicit type conversions..."

2. [0.64] Working with Unsafe (nomicon_working_with_unsafe)
   "Unsafe code must uphold certain invariants..."

------------------------------------------------------------
CLIPPY LINTS (3 matches)
------------------------------------------------------------
1. [0.82] cast_ptr_alignment [correctness]
   "Checks for casts from a less-aligned to more-aligned pointer"
   
2. [0.71] transmute_ptr_to_ptr [complexity]
   "Checks for transmutes between pointers to different types"

3. [0.65] ptr_as_ptr [pedantic]
   "Checks for as casts between raw pointers"

------------------------------------------------------------
SUGGESTED FLS QUERIES (LLM-generated)
------------------------------------------------------------
Based on matches, consider searching FLS for:
  • "type cast expression"
  • "pointer type raw"
  • "type coercion"
  • "alignment layout"

Search ID: a1b2c3d4-5678-90ab-cdef-1234567890ab
```

**Implementation Details:**

1. **Query Construction:**
   - If `--guideline`: Load MISRA guideline text from `misra_c_2025.json`
   - Combine title + rationale for embedding query
   - Display ADD-6 context if available

2. **Search Execution:**
   - Load embeddings for each enabled source
   - Compute cosine similarity against query embedding
   - Apply Clippy category weights before ranking
   - Merge and sort results by score

3. **LLM Query Suggestions:**
   - Extract top matches from each source
   - Prompt LLM: "Given these Rust documentation matches about [topic], suggest 4-5 search queries for finding related content in the Ferrocene Language Specification"
   - Fall back to keyword extraction if LLM unavailable

4. **Search ID:**
   - Generate UUID for tracking in `record-decision`

**Status:** [ ] Not started

**Subtasks:**
- [ ] Create `tools/src/fls_tools/rust_docs/search.py`
- [ ] Add entry point to `pyproject.toml`
- [ ] Implement multi-source search with weighting
- [ ] Implement LLM query suggestion (with fallback)
- [ ] Test with sample MISRA guidelines

---

### Phase 8: Workflow Integration

**Goal:** Update verification workflow to use context search.

**Updated Verification Protocol:**
```bash
# Step 0: Rust context search (NEW - always first)
uv run search-rust-context --guideline "Rule X.Y"

# Step 1: Deep FLS search  
uv run search-fls-deep --standard misra-c --guideline "Rule X.Y"

# Steps 2-4: Keyword FLS searches (informed by context suggestions)
uv run search-fls --query "<from context suggestions>" --top 10
uv run search-fls --query "<rust terminology>" --top 10
uv run search-fls --query "<additional angles>" --top 10
```

**Search Tracking (5 minimum searches now):**
```bash
uv run record-decision \
    --search-used "uuid1:search-rust-context:Rule 11.3:10" \
    --search-used "uuid2:search-fls-deep:Rule 11.3:5" \
    --search-used "uuid3:search-fls:type cast expression:10" \
    --search-used "uuid4:search-fls:pointer alignment:10" \
    --search-used "uuid5:search-fls:transmute undefined behavior:10" \
    ...
```

**AGENTS.md Updates Required:**
1. Add `search-rust-context` to tool documentation
2. Update "Phase 2: Analysis & Decision" to include Step 0
3. Update search protocol to require 5 searches (1 context + 4 FLS)
4. Document the 4 Rust documentation sources
5. Update `record-decision` examples with context search

**Note:** AGENTS.md changes require user approval before implementation.

**Status:** [ ] Not started

**Subtasks:**
- [ ] Draft AGENTS.md changes
- [ ] Get user approval for AGENTS.md changes
- [ ] Apply AGENTS.md updates
- [ ] Update decision file schema if needed (add `search-rust-context` to valid tools)

---

### Phase 9: Concept Crosswalk Enrichment

**Goal:** Enrich existing `concept_to_fls.json` with cross-references to new sources.

**Current File:** `coding-standards-fls-mapping/concept_to_fls.json`

**Current Structure (to preserve):**
```json
{
  "pointer": {
    "keywords": ["pointer", "raw pointer", "*const", "*mut"],
    "fls_ids": ["fls_...", "fls_..."]
  }
}
```

**Enriched Structure:**
```json
{
  "pointer cast": {
    "c_terms": ["pointer cast", "type punning", "(T*)expr"],
    "rust_terms": ["as cast", "raw pointer cast", "transmute"],
    "keywords": ["pointer cast", "type punning", "as cast", "transmute"],
    "fls_ids": ["fls_1qhsun1vyarz"],
    "reference_ids": ["ref_expressions_type_cast"],
    "ucg_ids": ["ucg_glossary_pointer_validity", "ucg_layout_structs"],
    "nomicon_ids": ["nomicon_casts", "nomicon_transmutes"],
    "clippy_lints": ["cast_ptr_alignment", "transmute_ptr_to_ptr"]
  }
}
```

**Approach:** 
1. Preserve existing `keywords` and `fls_ids` fields
2. Add new fields incrementally as we verify guidelines
3. During verification, when a good cross-reference is found, add it to crosswalk

**Schema Migration:**
- Existing entries keep working (backwards compatible)
- New entries can include additional source references
- Search tools use all available references

**Status:** [ ] Not started

**Subtasks:**
- [ ] Review current `concept_to_fls.json` structure
- [ ] Define schema for enriched entries
- [ ] Create tool or document process for adding cross-references during verification
- [ ] Migrate/enrich existing entries as verification proceeds

---

## Progress Tracking

### Overall Progress

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| 1 | Repository Acquisition | [ ] Not started | `clone-rust-docs` tool |
| 2 | Extract Reference | [ ] Not started | `extract-reference` tool |
| 3 | Extract UCG | [ ] Not started | `extract-ucg` tool |
| 4 | Extract Nomicon | [ ] Not started | `extract-nomicon` tool |
| 5 | Extract Clippy | [ ] Not started | `extract-clippy-lints` tool |
| 6 | Generate Embeddings | [ ] Not started | `generate-rust-embeddings` tool |
| 7 | Search Tool | [ ] Not started | `search-rust-context` tool |
| 8 | Workflow Integration | [ ] Not started | AGENTS.md updates (requires approval) |
| 9 | Concept Crosswalk | [ ] Not started | Enrich `concept_to_fls.json` |

### File Checklist

**New Package:**
- [ ] `tools/src/fls_tools/rust_docs/__init__.py`
- [ ] `tools/src/fls_tools/rust_docs/shared.py`
- [ ] `tools/src/fls_tools/rust_docs/clone.py`
- [ ] `tools/src/fls_tools/rust_docs/extract_reference.py`
- [ ] `tools/src/fls_tools/rust_docs/extract_ucg.py`
- [ ] `tools/src/fls_tools/rust_docs/extract_nomicon.py`
- [ ] `tools/src/fls_tools/rust_docs/extract_clippy.py`
- [ ] `tools/src/fls_tools/rust_docs/generate.py`
- [ ] `tools/src/fls_tools/rust_docs/search.py`

**Entry Points (pyproject.toml):**
- [ ] `clone-rust-docs`
- [ ] `extract-reference`
- [ ] `extract-ucg`
- [ ] `extract-nomicon`
- [ ] `extract-clippy-lints`
- [ ] `generate-rust-embeddings`
- [ ] `search-rust-context`

**Output Directories:**
- [ ] `cache/docs/` (cloned repos)
- [ ] `embeddings/reference/`
- [ ] `embeddings/ucg/`
- [ ] `embeddings/nomicon/`
- [ ] `embeddings/clippy/`

### Session Log

| Date | Session | Work Done |
|------|---------|-----------|
| 2026-01-03 | 1 | Created initial plan document |
| 2026-01-03 | 2 | Expanded plan with tool architecture and subtasks |

---

## Open Questions

1. **Embedding model verification:** What model are we currently using for FLS embeddings? Need to verify and document for consistency.
   - **Status:** TODO - check `tools/src/fls_tools/standards/embeddings/generate.py`

2. **Reference vs FLS overlap:** The Rust Reference and FLS cover similar ground. How do we handle overlap/deduplication in search results?
   - **Proposed:** Keep separate - Reference provides different perspective/explanation than FLS. Let user see both and decide which is more useful.

3. **Clippy version pinning:** Should we pin to a specific Clippy version, or always use latest?
   - **Proposed:** Use latest on initial clone. Record commit hash in extraction output. Re-clone periodically (manually triggered, not automatic).

4. **LLM for query suggestions:** Which LLM/API should be used for generating FLS query suggestions from context matches?
   - **Status:** TBD - could use Claude API, local model, or simple keyword extraction fallback

5. **Incremental updates:** How often should we refresh the cloned repos? On each verification session? Weekly?
   - **Proposed:** Manual refresh via `clone-rust-docs --update`. Not automatic. Record last update date in index.json.

6. **FLS clone consolidation:** Should existing `clone-fls` functionality move into the new `rust_docs` package?
   - **Decision:** Yes, consolidate. FLS is also upstream Rust documentation.

---

## Related Documents

- [`AGENTS.md`](../AGENTS.md) - Tool documentation and verification workflow
- [`docs/future/cross-reference-analysis.md`](future/cross-reference-analysis.md) - Future cross-reference plans
- [`coding-standards-fls-mapping/concept_to_fls.json`](../coding-standards-fls-mapping/concept_to_fls.json) - Existing concept mappings
