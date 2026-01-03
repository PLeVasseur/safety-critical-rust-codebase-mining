# FLS Paragraph Code Example Generation

> **Status:** DESIGN COMPLETE - Ready for Implementation
> 
> **Created:** 2026-01-03
> 
> **Purpose:** Generate compilable Rust code examples for FLS paragraphs to enable
> semantic matching between FLS specifications and the iceoryx2 codebase.

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Solution Architecture](#solution-architecture)
- [Storage Format](#storage-format)
- [Construct Vocabulary](#construct-vocabulary)
- [Tools](#tools)
- [Human Review Workflow](#human-review-workflow)
- [iceoryx2 Matching Pipeline](#iceoryx2-matching-pipeline)
- [Implementation Plan](#implementation-plan)
- [Open Questions](#open-questions)

---

## Overview

This system generates compilable Rust code examples for each FLS paragraph, extracts
"construct signatures" from those examples, and uses them to match against iceoryx2
source code. This creates a semantic bridge between abstract FLS specifications and
concrete code patterns.

```
FLS Paragraph (abstract spec)
         |
         v LLM generates
Canonical Code Examples (concrete patterns)
         |
         v Extract characteristics  
Pattern Signatures (queryable features)
         |
         v Match against
iceoryx2 codebase (target)
         |
         v Cross-reference with
MISRA-to-FLS mappings
         |
         v
Prioritized Guideline Writing Plan
```

### End Goal

Enable the cross-reference analysis (Pipeline 3) to answer:

> "Which MISRA guidelines are most relevant to iceoryx2, based on which FLS 
> constructs iceoryx2 actually uses?"

---

## Problem Statement

### Current Gap

We have two mapping efforts:

1. **MISRA -> FLS** (Pipeline 2): Maps safety guidelines to FLS section IDs
2. **iceoryx2 -> FLS** (Pipeline 1): Documents FLS construct usage with counts

**The gap:** Pipeline 1 uses regex/ripgrep for counting, which:
- Counts syntactic patterns, not semantic concepts
- Cannot distinguish between different uses of the same syntax
- Has no principled way to tie counts back to specific FLS paragraphs

### The Insight

LLM-generated code examples act as a **semantic bridge**:
- The LLM understands both FLS language AND Rust syntax
- Generated examples are "teaching examples" - they isolate the concept
- From those examples, we can extract structural/syntactic features
- Those features become our query patterns for matching against iceoryx2

---

## Solution Architecture

### High-Level Flow

```
+------------------------------------------------------------------+
|                    CONCEPT EXTRACTION PIPELINE                    |
+------------------------------------------------------------------+
|  FLS Paragraphs                                                   |
|       |                                                           |
|       v                                                           |
|  [LLM] Generate examples (valid, invalid, edge case)              |
|       |                                                           |
|       v                                                           |
|  [rustc] Verify compilation matches expectation                   |
|       |                                                           |
|       v                                                           |
|  [Human] Review and approve/reject examples                       |
|       |                                                           |
|       v                                                           |
|  [syn] Parse approved examples -> AST features                    |
|       |                                                           |
|       v                                                           |
|  Concept Signature (construct tags + fingerprint)                 |
|       |                                                           |
|       v                                                           |
|  Store: fls-examples/chapters/chapter_NN/                         |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|                    CODEBASE INDEXING PIPELINE                     |
+------------------------------------------------------------------+
|  iceoryx2 source files                                            |
|       |                                                           |
|       v                                                           |
|  [syn] Parse into code units (fns, impls, structs, etc.)          |
|       |                                                           |
|       v                                                           |
|  [syn] Compute syntactic fingerprint per unit                     |
|       |                                                           |
|       v                                                           |
|  Store: cache/iceoryx2-index/                                     |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|                       MATCHING PIPELINE                           |
+------------------------------------------------------------------+
|  For each FLS paragraph:                                          |
|    1. Get construct tags from approved examples                   |
|    2. Find iceoryx2 code units with matching constructs           |
|    3. Rank by fingerprint similarity                              |
|       |                                                           |
|       v                                                           |
|  Output: fls_to_iceoryx2_matches.json                             |
|  (fls_id -> [{code_unit, score, location}, ...])                  |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
|                    CROSS-REFERENCE OUTPUT                         |
+------------------------------------------------------------------+
|  Combine with MISRA -> FLS mapping:                               |
|                                                                   |
|  MISRA Rule X -> FLS paragraphs [a, b, c]                         |
|                     |                                             |
|                     v                                             |
|  FLS paragraphs [a, b, c] -> iceoryx2 code units [1, 2, ..., N]   |
|                     |                                             |
|                     v                                             |
|  Priority score = f(N, code_unit_importance, ...)                 |
+------------------------------------------------------------------+
```

---

## Storage Format

### Directory Structure

```
fls-examples/
+-- schema/
|   +-- example_metadata.schema.json    # JSON Schema for metadata files
|   +-- construct_vocabulary.schema.json
|
+-- constructs/
|   +-- vocabulary.json                 # Controlled vocabulary of constructs
|   +-- syn_mappings.json               # Map constructs to syn AST types
|
+-- chapters/
|   +-- chapter_04/                     # Types and Traits
|   |   +-- metadata.json               # Chapter-level metadata
|   |   +-- fls_abc123.json             # Per-paragraph metadata
|   |   +-- fls_abc123_valid_01.rs      # Code example files
|   |   +-- fls_abc123_valid_02.rs
|   |   +-- fls_abc123_invalid_01.rs
|   |   +-- fls_abc123_edge_01.rs
|   |   +-- ...
|   |
|   +-- chapter_15/                     # Ownership and Destruction
|       +-- metadata.json
|       +-- fls_xyz789.json
|       +-- fls_xyz789_valid_01.rs
|       +-- ...
|
+-- reviews/
|   +-- chapter_04_reviews.json         # Human review decisions
|   +-- chapter_15_reviews.json
|
+-- verification/
    +-- chapter_04_results.json         # Compilation test results
    +-- chapter_15_results.json
```

### Code Example File Format

Each `.rs` file is a standalone, compilable Rust program with metadata in doc comments:

```rust
//! FLS Example: fls_i1ny0k726a4a
//! Type: valid
//! Description: Sequential borrows - mutable reference ends before shared reference begins
//! Compile: pass
//! Edition: 2021
//! Constructs: mutable_reference, shared_reference, borrow_scope

# // Hidden setup code (for compilation only, not relevant to concept)
# #![allow(unused)]

fn main() {
    let mut x = 5;
    let r1 = &mut x;
    *r1 += 1;
    // r1 is no longer used after this point
    let r2 = &x;  // OK: mutable borrow has ended
    println!("{}", r2);
}
```

**Format conventions:**

| Element | Purpose |
|---------|---------|
| `//!` doc comments | Structured metadata, parseable by tools |
| `# ` prefix | Hidden lines (rustdoc convention) - excluded from fingerprint |
| Regular code | The "teaching content" - what demonstrates the FLS concept |

**Metadata fields:**

| Field | Required | Values |
|-------|----------|--------|
| `FLS Example` | Yes | FLS paragraph ID |
| `Type` | Yes | `valid`, `invalid`, `edge_case` |
| `Description` | Yes | Human-readable description |
| `Compile` | Yes | `pass`, `fail`, `warn` |
| `Edition` | No | `2015`, `2018`, `2021` (default: `2021`) |
| `Channel` | No | `stable`, `beta`, `nightly` (default: `stable`) |
| `Expected Error` | If `Compile: fail` | Error code (e.g., `E0502`) |
| `Constructs` | Yes | Comma-separated construct tags |

### Invalid Example Format

For examples that should NOT compile:

```rust
//! FLS Example: fls_i1ny0k726a4a
//! Type: invalid
//! Description: Overlapping mutable and shared references - compiler rejects
//! Compile: fail
//! Expected Error: E0502
//! Edition: 2021
//! Constructs: mutable_reference, shared_reference, borrow_conflict

fn main() {
    let mut x = 5;
    let r1 = &mut x;
    let r2 = &x;  // Error: cannot borrow `x` as immutable
    println!("{}, {}", r1, r2);
}
```

### Per-Paragraph Metadata JSON

```json
{
  "fls_id": "fls_i1ny0k726a4a",
  "fls_chapter": 15,
  "fls_section": "15.3",
  "fls_title": "References",
  "fls_text": "While a mutable reference is active, no other reference shall refer to a value that overlaps with the referent of the mutable reference.",
  "fls_category": -2,
  "generation_date": "2026-01-03",
  "generation_model": "claude-sonnet-4-20250514",
  "examples": [
    {
      "file": "fls_i1ny0k726a4a_valid_01.rs",
      "example_id": "ex_i1ny0k726a4a_valid_01",
      "type": "valid",
      "compile_expected": "pass"
    },
    {
      "file": "fls_i1ny0k726a4a_invalid_01.rs",
      "example_id": "ex_i1ny0k726a4a_invalid_01",
      "type": "invalid",
      "compile_expected": "fail",
      "expected_error": "E0502"
    },
    {
      "file": "fls_i1ny0k726a4a_edge_01.rs",
      "example_id": "ex_i1ny0k726a4a_edge_01",
      "type": "edge_case",
      "compile_expected": "pass"
    }
  ]
}
```

### Review File Format

```json
{
  "chapter": 15,
  "reviews": {
    "ex_i1ny0k726a4a_valid_01": {
      "status": "accepted",
      "reviewed_by": "human",
      "review_date": "2026-01-03",
      "comments": null,
      "construct_edits": null
    },
    "ex_i1ny0k726a4a_invalid_01": {
      "status": "rejected",
      "reviewed_by": "human",
      "review_date": "2026-01-03",
      "comments": "Example doesn't actually demonstrate the rule - add explicit lifetime",
      "construct_edits": null
    },
    "ex_i1ny0k726a4a_edge_01": {
      "status": "accepted",
      "reviewed_by": "human",
      "review_date": "2026-01-03",
      "comments": "Good demonstration of interior mutability escape hatch",
      "construct_edits": {
        "added": ["RefCell"],
        "removed": []
      }
    }
  }
}
```

---

## Construct Vocabulary

### Bootstrapping Sources

1. **`syn` crate AST types** - Foundation (~60 core types)
2. **Rust Reference section IDs** - Hierarchical concept organization
3. **FLS rubric categories** - Semantic groupings

### Initial Vocabulary Structure

```json
{
  "version": "1.0",
  "description": "Controlled vocabulary for FLS construct tagging",
  "categories": {
    "types": {
      "boolean_type": {
        "syn_nodes": ["TypePath"],
        "patterns": ["bool"],
        "reference_id": "type.bool"
      },
      "numeric_type": {
        "syn_nodes": ["TypePath"],
        "patterns": ["i8", "i16", "i32", "i64", "i128", "isize", "u8", "u16", "u32", "u64", "u128", "usize", "f32", "f64"],
        "reference_id": "type.numeric"
      },
      "reference_type": {
        "syn_nodes": ["TypeReference"],
        "reference_id": "type.pointer.ref"
      },
      "mutable_reference": {
        "syn_nodes": ["TypeReference"],
        "patterns": ["&mut"],
        "reference_id": "type.pointer.ref.mut"
      },
      "shared_reference": {
        "syn_nodes": ["TypeReference"],
        "patterns": ["&"],
        "reference_id": "type.pointer.ref.shared"
      }
    },
    "expressions": {
      "borrow_expression": {
        "syn_nodes": ["ExprReference"],
        "reference_id": "expr.borrow"
      },
      "dereference_expression": {
        "syn_nodes": ["ExprUnary"],
        "patterns": ["*"],
        "reference_id": "expr.deref"
      },
      "method_call": {
        "syn_nodes": ["ExprMethodCall"],
        "reference_id": "expr.method-call"
      }
    },
    "items": {
      "function_definition": {
        "syn_nodes": ["ItemFn"],
        "reference_id": "item.fn"
      },
      "struct_definition": {
        "syn_nodes": ["ItemStruct"],
        "reference_id": "item.struct"
      },
      "trait_definition": {
        "syn_nodes": ["ItemTrait"],
        "reference_id": "item.trait"
      },
      "impl_block": {
        "syn_nodes": ["ItemImpl"],
        "reference_id": "item.impl"
      }
    },
    "ownership": {
      "move_semantics": {
        "semantic": true,
        "description": "Value is moved (ownership transferred)"
      },
      "copy_semantics": {
        "semantic": true,
        "description": "Value is copied (implements Copy)"
      },
      "borrow_scope": {
        "semantic": true,
        "description": "Lifetime of a borrow"
      },
      "interior_mutability": {
        "syn_nodes": ["TypePath"],
        "patterns": ["Cell", "RefCell", "UnsafeCell", "Mutex", "RwLock"],
        "reference_id": "type.interior-mutability"
      }
    },
    "traits": {
      "trait_bound": {
        "syn_nodes": ["TraitBound"],
        "reference_id": "trait.bound"
      },
      "where_clause": {
        "syn_nodes": ["WhereClause"],
        "reference_id": "item.generics.where"
      },
      "associated_type": {
        "syn_nodes": ["TraitItemType", "ImplItemType"],
        "reference_id": "item.assoc.type"
      }
    },
    "generics": {
      "lifetime_parameter": {
        "syn_nodes": ["LifetimeParam", "Lifetime"],
        "reference_id": "item.generics.lifetime"
      },
      "type_parameter": {
        "syn_nodes": ["TypeParam"],
        "reference_id": "item.generics.type"
      },
      "const_generic": {
        "syn_nodes": ["ConstParam"],
        "reference_id": "item.generics.const"
      }
    }
  }
}
```

### Construct Matching Rules

| Construct Type | Detection Method |
|----------------|------------------|
| **Syntactic** | Direct `syn` AST node matching |
| **Pattern-based** | AST node + text pattern matching |
| **Semantic** | Requires context analysis or is manually tagged |

---

## Tools

### Tool 1: `generate-fls-examples`

Generates code examples for FLS paragraphs using an LLM.

```bash
cd tools
uv run generate-fls-examples \
    --chapter 15 \
    --paragraph fls_i1ny0k726a4a \
    --examples-per-paragraph 3
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--chapter` | Required | FLS chapter number |
| `--paragraph` | All | Specific paragraph ID (optional) |
| `--examples-per-paragraph` | 3 | Number of examples to generate |
| `--types` | `valid,invalid,edge_case` | Types to generate |
| `--force` | False | Regenerate existing examples |
| `--dry-run` | False | Show prompts without generating |

**Output:** Creates `.rs` files and `.json` metadata in `fls-examples/chapters/chapter_NN/`

### Tool 2: `verify-fls-examples`

Compiles all examples and verifies results match expectations.

```bash
cd tools
uv run verify-fls-examples --chapter 15
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--chapter` | All | Specific chapter to verify |
| `--fix-metadata` | False | Auto-fix incorrect compile expectations |
| `--report` | False | Generate summary report only |

**Output:** `fls-examples/verification/chapter_NN_results.json`

**Verification logic:**

| Expected | Actual | Result |
|----------|--------|--------|
| `pass` | Compiles | PASS |
| `pass` | Fails | FAIL - needs review |
| `fail` | Compiles | FAIL - example doesn't demonstrate rule |
| `fail` | Fails with expected error | PASS |
| `fail` | Fails with different error | WARN - check error code |

### Tool 3: `review-fls-examples`

Interactive human review interface.

```bash
cd tools
uv run review-fls-examples \
    --chapter 15 \
    --status pending \
    --interactive
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--chapter` | Required | Chapter to review |
| `--status` | `pending` | Filter by status: `pending`, `accepted`, `rejected`, `all` |
| `--interactive` | False | Interactive review mode |
| `--report` | False | Generate summary report |
| `--paragraph` | All | Review specific paragraph only |

**Interactive commands:**

| Key | Action |
|-----|--------|
| `A` | Accept example |
| `R` | Reject example (prompts for comment) |
| `E` | Edit construct tags |
| `C` | Add comment without decision |
| `S` | Skip to next example |
| `Q` | Save progress and quit |

**Output:** Updates `fls-examples/reviews/chapter_NN_reviews.json`

### Tool 4: `extract-construct-fingerprints`

Parses approved examples and extracts construct fingerprints.

```bash
cd tools
uv run extract-construct-fingerprints --chapter 15
```

**What it does:**
1. Loads all examples with `status: accepted`
2. Parses each `.rs` file with `syn` (excluding `# ` hidden lines)
3. Extracts AST features matching construct vocabulary
4. Validates declared constructs against detected constructs
5. Stores fingerprints for matching

**Output:** `fls-examples/chapters/chapter_NN/fingerprints.json`

### Tool 5: `index-iceoryx2`

Builds a searchable index of iceoryx2 code units.

```bash
cd tools
uv run index-iceoryx2 --version 0.8.0
```

**What it does:**
1. Parses all `.rs` files in iceoryx2 with `syn`
2. Extracts code units (functions, impl blocks, structs, etc.)
3. Computes construct fingerprint for each unit
4. Stores as searchable index

**Output:** `cache/iceoryx2-index/v0.8.0/index.json`

### Tool 6: `match-fls-to-iceoryx2`

Matches FLS paragraphs to iceoryx2 code based on construct similarity.

```bash
cd tools
uv run match-fls-to-iceoryx2 \
    --chapter 15 \
    --threshold 0.5
```

**Matching algorithm:**
1. For each FLS paragraph with approved examples:
   - Get union of construct tags from all examples
   - Find iceoryx2 code units with overlapping constructs
   - Rank by Jaccard similarity of construct sets
2. Output matches above threshold

**Output:** `cache/analysis/fls_to_iceoryx2_matches.json`

---

## Human Review Workflow

### Review Interface

```
================================================================
FLS PARAGRAPH: fls_i1ny0k726a4a
----------------------------------------------------------------
Chapter: 15 - Ownership and Destruction
Section: 15.3 - References
Category: Legality Rules

TEXT:
  "While a mutable reference is active, no other reference shall 
   refer to a value that overlaps with the referent of the mutable 
   reference."

================================================================
EXAMPLE 1 of 3: ex_i1ny0k726a4a_valid_01
----------------------------------------------------------------
Type: valid
Description: Sequential borrows - mutable reference ends before 
             shared reference begins
Expected: pass

CODE:
+------------------------------------------------------------------+
| fn main() {                                                      |
|     let mut x = 5;                                               |
|     let r1 = &mut x;                                             |
|     *r1 += 1;                                                    |
|     // r1 is no longer used after this point                     |
|     let r2 = &x;  // OK: mutable borrow has ended                |
|     println!("{}", r2);                                          |
| }                                                                |
+------------------------------------------------------------------+

Compilation: PASS (as expected)

Constructs: mutable_reference, shared_reference, borrow_scope

----------------------------------------------------------------
[A]ccept  [R]eject  [E]dit constructs  [C]omment  [S]kip  [Q]uit
> 
```

### Review Report

```
FLS Chapter 15: Ownership and Destruction
=========================================

Paragraphs: 151
Examples generated: 453 (3 per paragraph)

Review Status:
  Accepted:  234 (52%)
  Rejected:   45 (10%)
  Pending:   174 (38%)

Compilation Results:
  Pass (expected):     312
  Fail (expected):      89
  Pass (unexpected):    12  <- Need review
  Fail (unexpected):    40  <- Need regeneration

Top Rejection Reasons:
  - 15: Example doesn't demonstrate the specific rule
  - 12: Missing necessary context/setup
  - 8: Wrong error code expected
  - 5: Construct tags incomplete
  - 5: Example too complex

Construct Coverage:
  mutable_reference: 89 examples
  shared_reference: 76 examples
  lifetime_parameter: 45 examples
  borrow_scope: 34 examples
  interior_mutability: 12 examples
```

---

## iceoryx2 Matching Pipeline

### Matching Strategy

The matching uses a multi-level approach:

**Level 1: Construct Set Filtering (Fast)**
- Find code units with ANY overlap in construct tags
- Prunes ~90% of code units

**Level 2: Construct Similarity (Medium)**
- Jaccard similarity of construct sets
- `J(A, B) = |A ∩ B| / |A ∪ B|`
- Threshold: 0.3 (configurable)

**Level 3: Structural Patterns (Optional)**
- For high-confidence matches, verify structural patterns
- E.g., "mutable reference followed by shared reference to same variable"

### Match Output Format

```json
{
  "fls_id": "fls_i1ny0k726a4a",
  "fls_title": "References - Mutable reference exclusivity",
  "construct_signature": ["mutable_reference", "shared_reference", "borrow_scope"],
  "matches": [
    {
      "code_unit_id": "iceoryx2::waitset::WaitSet::wait_and_process",
      "file": "iceoryx2/src/waitset.rs",
      "line_start": 580,
      "line_end": 620,
      "constructs_matched": ["mutable_reference", "shared_reference"],
      "similarity_score": 0.67,
      "snippet": "pub fn wait_and_process<F>(&self, handler: F) -> Result<...>"
    },
    {
      "code_unit_id": "iceoryx2_bb::posix::mutex::MutexGuard::deref_mut",
      "file": "iceoryx2-bb/posix/src/mutex.rs",
      "line_start": 195,
      "line_end": 198,
      "constructs_matched": ["mutable_reference", "borrow_scope"],
      "similarity_score": 0.50,
      "snippet": "fn deref_mut(&mut self) -> &mut Self::Target { ... }"
    }
  ],
  "match_count": 45,
  "top_files": [
    {"file": "iceoryx2/src/waitset.rs", "matches": 12},
    {"file": "iceoryx2-bb/posix/src/mutex.rs", "matches": 8}
  ]
}
```

---

## Implementation Plan

### Phase 1: Infrastructure Setup (Week 1)

1. **Create directory structure**
   - `fls-examples/` with subdirectories
   - JSON schemas for metadata files

2. **Create construct vocabulary**
   - Bootstrap from Reference section IDs
   - Add `syn` AST type mappings
   - Define initial ~100 constructs

3. **Implement core tools**
   - `generate-fls-examples` (LLM generation)
   - `verify-fls-examples` (compilation checking)
   - `review-fls-examples` (human review interface)

### Phase 2: Chapter 4 Proof of Concept (Week 2)

1. **Generate examples for Chapter 4 (Types and Traits)**
   - ~100 paragraphs
   - 3 examples each = ~300 examples

2. **Run verification**
   - Fix compilation issues
   - Iterate on generation prompt

3. **Human review cycle**
   - Accept/reject examples
   - Refine construct tags
   - Track rejection patterns

4. **Assess quality metrics**
   - Compilation pass rate
   - Acceptance rate
   - Construct coverage

### Phase 3: Chapter 15 and Validation (Week 3)

1. **Generate examples for Chapter 15 (Ownership and Destruction)**
   - ~150 paragraphs
   - More semantic concepts (ownership, borrowing)

2. **Validate construct vocabulary**
   - Are existing constructs sufficient?
   - Add new constructs as needed

3. **Human review cycle**

4. **Cross-validate**
   - Compare extracted constructs to existing iceoryx2-FLS mapping counts
   - Identify gaps in coverage

### Phase 4: iceoryx2 Matching (Week 4)

1. **Build iceoryx2 index**
   - Parse v0.8.0 codebase
   - Extract code unit fingerprints

2. **Implement matching**
   - Construct-based matching algorithm
   - Threshold tuning

3. **Generate cross-reference report**
   - FLS paragraph -> iceoryx2 locations
   - Aggregate by MISRA guideline

4. **Validate against known mappings**
   - Compare match counts to existing Pipeline 1 statistics
   - Identify discrepancies

---

## Open Questions

### Technical

1. **Rust edition handling:** Should examples default to 2021 or match iceoryx2's MSRV?

2. **Hidden line heuristics:** What setup code is commonly needed? Should we have templates?

3. **Construct granularity:** How fine-grained should constructs be? 
   - Too coarse: Poor matching precision
   - Too fine: Sparse matches, complex vocabulary

4. **Semantic constructs:** How to handle constructs that can't be detected syntactically?
   - Option A: Rely on LLM tagging (what we do now)
   - Option B: Add heuristics (e.g., "if Drop is implemented, tag as drop_semantics")
   - Option C: Accept that some constructs are manual-only

### Process

5. **Review throughput:** With ~3,700 FLS paragraphs x 3 examples = ~11,000 examples, 
   how do we scale human review?
   - Option A: Prioritize chapters by MISRA relevance
   - Option B: Sample-based review (review 10% per chapter)
   - Option C: Accept LLM-only for low-priority chapters

6. **Regeneration policy:** When do we regenerate rejected examples?
   - After N rejections for same reason?
   - With updated prompts?
   - Manual trigger only?

7. **Vocabulary evolution:** How do we handle construct vocabulary changes?
   - Re-tag existing examples?
   - Grandfather old tags?
   - Version the vocabulary?

---

## Appendix: LLM Generation Prompt Template

```
You are generating Rust code examples to demonstrate FLS (Ferrocene Language 
Specification) paragraph concepts.

## FLS Paragraph

**ID:** {fls_id}
**Chapter:** {chapter} - {chapter_title}
**Section:** {section}
**Text:** {fls_text}

## Task

Generate {count} code examples for this FLS paragraph:
1. One **valid** example that compiles and demonstrates correct usage
2. One **invalid** example that fails to compile (demonstrating what the rule prevents)
3. One **edge case** example showing boundary behavior or escape hatches

## Requirements

- Each example must be a complete, standalone Rust program with `fn main()`
- Use Rust 2021 edition unless the concept requires otherwise
- Keep examples minimal - focus on demonstrating the specific FLS concept
- Use rustdoc `# ` prefix for boilerplate that's needed for compilation but not 
  relevant to the concept being demonstrated
- Include clear comments explaining what the example demonstrates

## Output Format

For each example, provide:
1. Metadata header as `//!` doc comments
2. The Rust code
3. For invalid examples, specify the expected error code

## Construct Tags

From this vocabulary, select ALL constructs demonstrated in each example:
{construct_vocabulary_subset}

## Example Output

```rust
//! FLS Example: {fls_id}
//! Type: valid
//! Description: [Brief description of what this demonstrates]
//! Compile: pass
//! Edition: 2021
//! Constructs: [comma-separated construct tags]

fn main() {
    // Example code here
}
```
```

---

## References

- [Ferrocene Language Specification](https://spec.ferrocene.dev/)
- [Safety-Critical Rust Coding Guidelines](https://github.com/rustfoundation/safety-critical-rust-coding-guidelines)
- [syn crate documentation](https://docs.rs/syn/)
- [The Rust Reference](https://doc.rust-lang.org/reference/)
