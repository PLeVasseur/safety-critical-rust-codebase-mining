# Verification Comparison Analysis Plan

**Date:** 2026-01-08
**Status:** In Progress - Processing 145 Outliers

## Overview

This plan describes tools and workflows for comparing the new verification decision files (batches 1, 2, 3) against the current mapping file to assess:

1. What categorizations changed vs MISRA ADD-6
2. Which FLS paragraphs were added/removed and why
3. Whether quality improved overall
4. Whether batch definitions predicted verification outcomes
5. Systematic patterns across batches

## Design Principles

### Context-Preserving Analysis

**Problem:** Analyzing 50+ outliers exhausts LLM context after ~5-10 detailed reviews. Cross-batch patterns require remembering details from earlier outliers.

**Solution:** Record each outlier analysis to a self-contained file with full context (ADD-6, MISRA text, FLS content excerpts, mapping/decision state). This allows:
- Incremental analysis across multiple sessions
- Batch and cross-batch synthesis from recorded judgments
- Audit trail of analysis decisions

### Hierarchical Markdown Reports

Human review follows a drill-down pattern:
1. **Final report** (`final_report.md`) - Executive summary with highlights
2. **Per-batch reports** (`batch{N}_report.md`) - Detailed batch analysis
3. **Cross-batch report** (`cross_batch_report.md`) - Systematic patterns
4. **Individual outlier JSONs** - Full context for deep inspection

### Gated Apply Process

The `apply-verification` tool is extended to require analysis completion before applying decisions, ensuring human review happened.

---

## Output Directory Structure

```
cache/analysis/
├── comparison_data/           # Raw extracted comparison data
│   ├── batch1/
│   │   ├── Dir_4.3.json
│   │   └── ...
│   ├── batch2/
│   │   └── ...
│   ├── batch3/
│   │   └── ...
│   ├── batch1_summary.json
│   ├── batch2_summary.json
│   ├── batch3_summary.json
│   └── cross_batch_summary.json
├── outlier_analysis/          # Per-outlier analysis records with judgments
│   ├── Rule_10.1.json
│   ├── Dir_4.6.json
│   └── ...
├── reports/                   # Human-readable Markdown reports
│   ├── final_report.md        # Executive summary
│   ├── batch1_report.md       # Batch 1 detailed report
│   ├── batch2_report.md       # Batch 2 detailed report
│   ├── batch3_report.md       # Batch 3 detailed report
│   └── cross_batch_report.md  # Cross-batch patterns report
└── review_state.json          # Tracks interactive review progress
```

**Note:** Files in `cache/` contain copyrighted MISRA content and must be deleted after analysis is complete.

---

## Current State

### Mapping File (`coding-standards-fls-mapping/mappings/misra_c_to_fls.json`)

| Schema | Count | Description |
|--------|-------|-------------|
| v1.1 | 77 | Original automated mappings + ADD-6 enrichment |
| v2.1 | 108 | Prior verification work (per-context structure) |
| v3.0 | 38 | Prior v3 verification work |
| **Total** | **223** | |

### Decision Files (`cache/verification/misra-c/batch*_decisions/`)

| Batch | Count | Decision Schema | Has `analysis_summary` |
|-------|-------|-----------------|------------------------|
| 1 | 20 | v3.0 | No |
| 2 | 118 | v3.1 | Yes |
| 3 | 7 | v3.1 | Yes |
| **Total** | **145** | | |

### Batch Definitions

| Batch | Name | Guidelines | Expected Pattern |
|-------|------|------------|------------------|
| 1 | High-score direct mappings | 20 | `applicability=yes`, `rationale_type=direct_mapping` |
| 2 | Not applicable | 118 | `applicability=no`, `rationale_type=no_equivalent` |
| 3 | Stdlib & Resources | 7 | `all_rust`: `applicability=yes`; `safe_rust`: often `applicability=no` |

---

## Tools Summary

| Tool | Purpose | Output |
|------|---------|--------|
| `extract-comparison-data` | Extract raw comparison data, compute flags | Per-guideline JSON + summaries |
| `record-outlier-analysis` | Record LLM analysis for one outlier (with per-FLS-ID detail) | Outlier analysis JSON |
| `list-pending-outliers` | Show outliers not yet analyzed by LLM | stdout |
| `diff-fls-matches` | Human-readable diff for quick review | stdout |
| `generate-analysis-reports` | Generate all Markdown reports | Markdown files |
| `review-outliers` | Interactive human review with granular per-aspect decisions | Updates review_state.json |
| `apply-verification` (extended) | Apply decisions with analysis gate and granular filtering | Updates mapping file |

### Review Granularity

The `review-outliers` tool prompts separately for each flagged aspect:

| Aspect | Granularity | Bulk Action Available |
|--------|-------------|----------------------|
| Categorization change | Per-guideline | `--accept-categorization-pattern` |
| FLS removals | Per-FLS-ID | `--accept-removal <fls_id>` |
| FLS additions | Per-FLS-ID | `--accept-addition <fls_id>` |
| ADD-6 divergence | Per-guideline | N/A |

Human can accept/reject at any level:
- Accept all removals for a guideline
- Accept specific removal, reject others
- Pre-accept removal of specific FLS ID across all guidelines (bulk rule)

---

## Tool Specifications

### 1. `extract-comparison-data`

**Purpose:** Extract and normalize data from all sources, compute flags and comparison diffs.

**Command:**
```bash
uv run extract-comparison-data --standard misra-c --batches 1,2,3
```

**Outputs:**
- `cache/analysis/comparison_data/batch{N}/{guideline}.json` - Per-guideline raw data (without FLS content)
- `cache/analysis/comparison_data/batch{N}_summary.json` - Batch statistics
- `cache/analysis/comparison_data/cross_batch_summary.json` - Cross-batch patterns

**Per-guideline JSON structure:**
```json
{
  "guideline_id": "Rule 10.1",
  "batch": 2,
  "guideline_type": "Rule",
  "misra_chapter": 10,
  "add6": {
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "required",
    "rationale_codes": ["UB"],
    "comment": ""
  },
  "mapping": {
    "schema_version": "2.1",
    "all_rust": {
      "applicability": "yes",
      "adjusted_category": "required",
      "rationale_type": "direct_mapping",
      "confidence": "high",
      "accepted_matches": [...],
      "rejected_matches": [...],
      "notes": "..."
    },
    "safe_rust": { ... }
  },
  "decision": {
    "schema_version": "3.1",
    "all_rust": {
      "decision": "accept_with_modifications",
      "applicability": "no",
      "adjusted_category": "n_a",
      "rationale_type": "no_equivalent",
      "confidence": "high",
      "analysis_summary": { ... },
      "accepted_matches": [...],
      "rejected_matches": [...],
      "search_tools_used": [...],
      "notes": "..."
    },
    "safe_rust": { ... }
  },
  "comparison": {
    "all_rust": {
      "applicability_changed": true,
      "applicability_mapping_to_decision": "yes → no",
      "applicability_differs_from_add6": true,
      "adjusted_category_changed": true,
      "adjusted_category_mapping_to_decision": "required → n_a",
      "rationale_type_changed": true,
      "rationale_type_mapping_to_decision": "direct_mapping → no_equivalent",
      "fls_added": ["fls_xyz789"],
      "fls_removed": ["fls_def456"],
      "fls_retained": ["fls_abc123"],
      "net_fls_change": 0
    },
    "safe_rust": { ... }
  },
  "flags": {
    "applicability_differs_from_add6": true,
    "adjusted_category_differs_from_add6": true,
    "fls_removed": true,
    "fls_added": false,
    "specificity_decreased": false,
    "rationale_type_changed": true,
    "batch_pattern_outlier": true,
    "missing_analysis_summary": false,
    "missing_search_tools": false,
    "multi_dimension_outlier": true
  }
}
```

---

### 2. `record-outlier-analysis`

**Purpose:** Record LLM analysis judgment for one outlier with full embedded context, per-FLS-ID detail, and context information for human review.

**Command:**
```bash
uv run record-outlier-analysis \
    --standard misra-c \
    --guideline "Rule 10.1" \
    --batch 2 \
    --analysis-summary "MISRA Rule 10.1 addresses essential type model for operators..." \
    --categorization-verdict appropriate \
    --categorization-reasoning "The change from yes→no is appropriate because..." \
    --fls-removals-verdict appropriate \
    --fls-removals-reasoning "Overall: these removals are appropriate because..." \
    --fls-removal-detail "fls_def456:all_rust:Too generic for this specific concern" \
    --fls-removal-detail "fls_abc789:both:Not relevant to essential type model" \
    --fls-additions-verdict appropriate \
    --fls-additions-reasoning "Overall: these additions are appropriate because..." \
    --fls-addition-detail "fls_xyz789:all_rust:More specific to integer semantics" \
    --add6-divergence-verdict justified \
    --add6-divergence-reasoning "ADD-6 says Yes but Rust has no essential type model..." \
    --specificity-verdict appropriate \
    --specificity-reasoning "Replaced with equivalent paragraph-level matches" \
    --overall-recommendation accept \
    [--routine-pattern "generic section removal"] \
    [--notes "Optional notes"]
```

**Required parameters:**
- `--standard`: The coding standard (misra-c, etc.)
- `--guideline`: Guideline ID (e.g., "Rule 10.1")
- `--batch`: Batch number (1, 2, or 3)
- `--analysis-summary`: Brief summary of MISRA concern and how Rust handles it
- `--overall-recommendation`: One of `accept`, `accept_with_notes`, `needs_review`, `reject`

**Conditional parameters (based on flags):**
- `--categorization-verdict` + `--categorization-reasoning`: Required if `rationale_type_changed` or `batch_pattern_outlier` flag
- `--fls-removals-verdict` + `--fls-removals-reasoning`: Required if `fls_removed` flag
- `--fls-removal-detail`: Required for each removed FLS ID (format: `fls_id:context:justification`)
- `--fls-additions-verdict` + `--fls-additions-reasoning`: Required if `fls_added` flag
- `--fls-addition-detail`: Required for each added FLS ID (format: `fls_id:context:justification`)
- `--add6-divergence-verdict` + `--add6-divergence-reasoning`: Required if `applicability_differs_from_add6` or `adjusted_category_differs_from_add6` flag
- `--specificity-verdict` + `--specificity-reasoning`: Required if `specificity_decreased` flag

**Per-FLS-ID detail format:**
```
fls_id:context:justification
```
Where `context` is one of:
- `all_rust` - FLS ID only in all_rust context
- `safe_rust` - FLS ID only in safe_rust context  
- `both` - FLS ID in both contexts

**Verdict options:**
- `categorization-verdict`: `appropriate | inappropriate | needs_review`
- `fls-removals-verdict`: `appropriate | inappropriate | needs_review | n_a`
- `fls-additions-verdict`: `appropriate | inappropriate | needs_review | n_a`
- `add6-divergence-verdict`: `justified | questionable | incorrect | n_a` (note: `n_a` rejected if divergence flags are set)
- `specificity-verdict`: `appropriate | inappropriate | needs_review | n_a`
- `overall-recommendation`: `accept | accept_with_notes | needs_review | reject`

**Behavior:**
1. Loads comparison data from `cache/analysis/comparison_data/`
2. Validates guideline is actually flagged
3. Loads full context: ADD-6, MISRA extracted text, FLS content excerpts (section content + relevant rubrics)
4. Embeds all context into the analysis file
5. **Auto-determines context** for each FLS ID from comparison data (validates against provided context)
6. Writes to `cache/analysis/outlier_analysis/{guideline_id}.json`

**Conditional parameters:**
- `--fls-removals-*` required only if guideline has FLS removals
- `--fls-additions-*` required only if guideline has FLS additions
- `--add6-divergence-*` required only if guideline diverges from ADD-6
- `--specificity-*` required only if specificity_decreased flag is set

**Per-FLS-ID detail parameters:**
- `--fls-removal-detail "fls_id:context:justification"` - Required for each removed FLS ID
- `--fls-addition-detail "fls_id:context:justification"` - Required for each added FLS ID

The `context` must be one of `all_rust`, `safe_rust`, or `both`. The tool validates that the FLS ID actually appears in the specified context(s) from comparison data.

These per-ID justifications with context information enable the human reviewer to make granular per-context accept/reject decisions on individual FLS changes.

#### ADD-6 Divergence Analysis

When analyzing ADD-6 divergence, follow this process:

1. **Check top-level flags first:**
   - `flags.applicability_differs_from_add6`
   - `flags.adjusted_category_differs_from_add6`
   
   If EITHER is `true`, there IS a divergence that must be addressed.

2. **Identify which context(s) diverge:**
   Check `comparison.all_rust` and `comparison.safe_rust` for:
   - `applicability_differs_from_add6: true`
   - `adjusted_category_differs_from_add6: true`

3. **Compare values:**
   For each diverging context, compare:
   - ADD-6 value: `add6.applicability_all_rust` or `add6.applicability_safe_rust`
   - Decision value: `decision.{context}.applicability`

4. **Determine verdict:**
   - `justified`: The divergence is intentional AND correct (e.g., ADD-6 is wrong, or Rust semantics differ)
   - `questionable`: The divergence may be wrong and needs human review
   - `incorrect`: The divergence is clearly wrong and should be fixed
   - `n_a`: **ONLY valid when top-level divergence flags are FALSE** - the tool will reject `n_a` if divergence flags are set

5. **Document reasoning per context:**
   The reasoning should explain WHY each diverging context's decision differs from ADD-6.

**Example (Dir 4.3):**
```
Flags show: applicability_differs_from_add6=true
Context analysis:
  - all_rust: applicability=yes matches ADD-6=Yes ✓
  - safe_rust: applicability=no DIFFERS from ADD-6=Yes ✗

Verdict: justified
Reasoning: Safe Rust cannot use asm! macros (FLS fls_s5nfhBFOk8Bu lists 'Calling 
macro core::arch::asm' as an unsafe operation). ADD-6 appears to be incorrect 
for safe_rust context - the guideline is not applicable when assembly is 
impossible.
```

**Common ADD-6 Divergence Patterns:**

| Pattern | Verdict | Typical Reasoning |
|---------|---------|-------------------|
| Safe Rust prevents the concern entirely | `justified` | FLS shows Rust's type system/borrow checker prevents the issue |
| Unsafe-only operation | `justified` | Operation requires `unsafe`, so safe_rust applicability should be `no` |
| Different Rust semantics | `justified` | Rust handles the concept differently than C |
| Potential ADD-6 error | `questionable` | ADD-6 may have incorrect applicability |
| Decision appears wrong | `incorrect` | The verification decision should be updated to match ADD-6 |

**Output file structure:**

The outlier analysis file contains three main sections:
1. **`context`** - Full embedded context (ADD-6, MISRA text, FLS content)
2. **`analysis`** - LLM analysis and verdicts (written by `record-outlier-analysis`)
3. **`human_review`** - Human decisions (written by `review-outliers`)

```json
{
  "guideline_id": "Rule 10.1",
  "batch": 2,
  "analysis_date": "2026-01-08",
  
  "context": {
    "add6": {
      "applicability_all_rust": "Yes",
      "applicability_safe_rust": "No",
      "adjusted_category": "required",
      "rationale_codes": ["UB"],
      "comment": "Full ADD-6 comment..."
    },
    "misra_extracted": {
      "headline": "Operands shall not be of an inappropriate essential type",
      "rationale": "Full rationale text from PDF...",
      "amplification": "Full amplification text..."
    },
    "mapping": {
      "schema_version": "2.1",
      "all_rust": {
        "applicability": "yes",
        "adjusted_category": "required",
        "rationale_type": "direct_mapping",
        "confidence": "high",
        "accepted_matches": [
          {
            "fls_id": "fls_abc123",
            "fls_title": "Arithmetic Expressions",
            "category": 0,
            "score": 0.65,
            "reason": "Maps to essential type arithmetic",
            "fls_content": "Full section content...",
            "fls_rubrics": {
              "-2": ["Legality rule paragraph 1...", "Legality rule paragraph 2..."]
            }
          }
        ],
        "rejected_matches": []
      },
      "safe_rust": { ... }
    },
    "decision": {
      "schema_version": "3.1",
      "all_rust": {
        "applicability": "no",
        "adjusted_category": "n_a",
        "rationale_type": "no_equivalent",
        "confidence": "high",
        "analysis_summary": {
          "misra_concern": "...",
          "rust_analysis": "..."
        },
        "accepted_matches": [
          {
            "fls_id": "fls_xyz789",
            "fls_title": "Integer Types",
            "category": 0,
            "score": 0.55,
            "reason": "Defines integer type semantics...",
            "fls_content": "Full section content...",
            "fls_rubrics": {
              "-2": ["Relevant legality rules..."]
            }
          }
        ],
        "rejected_matches": []
      },
      "safe_rust": { ... }
    },
    "comparison": {
      "all_rust": {
        "fls_added": ["fls_xyz789"],
        "fls_removed": ["fls_def456"],
        "fls_retained": ["fls_abc123"],
        "applicability_changed": true,
        "rationale_type_changed": true
      },
      "safe_rust": { ... }
    }
  },
  
  "flags": ["applicability_differs_from_add6", "fls_removed", "batch_pattern_outlier"],
  
  "analysis": {
    "categorization": {
      "verdict": "appropriate",
      "reasoning": "..."
    },
    "fls_removals": {
      "verdict": "appropriate",
      "reasoning": "...",
      "per_id": {
        "fls_def456": {
          "title": "Type Coercion",
          "removal_justification": "Too generic..."
        }
      }
    },
    "fls_additions": {
      "verdict": "appropriate",
      "reasoning": "...",
      "per_id": {
        "fls_xyz789": {
          "title": "Integer Types",
          "addition_justification": "More specific..."
        }
      }
    },
    "add6_divergence": {
      "verdict": "justified",
      "reasoning": "..."
    },
    "overall_verdict": "accept",
    "routine_pattern": null,
    "notes": "..."
  },
  
  "human_review": {
    "reviewed_at": "2026-01-08T14:30:00Z",
    "categorization": {
      "decision": "accept",
      "notes": null
    },
    "fls_removals": {
      "fls_def456": {
        "decision": "accept",
        "via_bulk_rule": false
      }
    },
    "fls_additions": {
      "fls_xyz789": {
        "decision": "accept",
        "via_bulk_rule": false
      }
    },
    "add6_divergence": {
      "decision": "accept",
      "notes": null
    },
    "overall_status": "fully_reviewed"
  }
}
```

**Note:** The `human_review` section is initially absent. It is added by `review-outliers` when the human reviews the outlier.

**Verdict options:**
- `categorization`: `appropriate | inappropriate | needs_review`
- `fls_removals`: `appropriate | inappropriate | needs_review | n_a`
- `fls_additions`: `appropriate | inappropriate | needs_review | n_a`
- `add6_divergence`: `justified | questionable | incorrect | n_a`
- `overall_verdict`: `accept | revise | flag_for_human`

**Per-FLS-ID detail in analysis (for granular human review):**

When FLS IDs are removed or added, the analysis file includes per-ID information with context to support granular per-context human decisions:

```json
{
  "llm_analysis": {
    "fls_removals": {
      "verdict": "inappropriate",
      "reasoning": "Overall reasoning for removals...",
      "per_id": {
        "fls_3fg60jblx0xb": {
          "title": "Inline Assembly legality",
          "category": -2,
          "contexts": ["all_rust"],
          "original_reason": "Per FLS: 'Inline assembly is written as...'",
          "removal_decisions": {
            "all_rust": "Keep - directly relevant legality rule"
          }
        },
        "fls_4lb6yh12w1cv": {
          "title": "asm macro invocation",
          "category": -2,
          "contexts": ["all_rust"],
          "original_reason": "Per FLS: 'Invoking macro core::arch::asm...'",
          "removal_decisions": {
            "all_rust": "Keep - asm macro rule is essential"
          }
        }
      }
    },
    "fls_additions": {
      "verdict": "appropriate",
      "reasoning": "Overall reasoning for additions...",
      "per_id": {
        "fls_s5nfhBFOk8Bu": {
          "title": "Unsafety legality rule",
          "category": -2,
          "contexts": ["all_rust"],
          "new_reason": "Unsafety context requirement for asm!",
          "addition_decisions": {
            "all_rust": "Relevant - shows unsafe context requirement"
          }
        }
      }
    }
  }
}
```

The `contexts` array indicates which context(s) the FLS ID appears in. The `removal_decisions` and `addition_decisions` dicts are keyed by context, allowing different justifications per context. This enables the human reviewer to accept/reject individual FLS changes per-context rather than all-or-nothing.

---

### 3. `list-pending-outliers`

**Purpose:** Show flagged guidelines that don't yet have an analysis file.

**Command:**
```bash
uv run list-pending-outliers [--batch N] [--flag-type TYPE]
```

**Flag types:** `categorization`, `fls-removed`, `fls-added`, `pattern`, `multi`, `all`

**Output:**
```
=== Pending Outliers ===

Batch 1 (5 pending / 8 total flagged):
  Dir 4.3: fls_removed, categorization
  Rule 11.1: fls_added
  ...

Batch 2 (42 pending / 45 total flagged):
  Rule 10.1: applicability_differs_from_add6, fls_removed, batch_pattern_outlier [MULTI]
  ...
```

---

### 4. `diff-fls-matches`

**Purpose:** Human-readable diff for quick visual review.

**Command:**
```bash
uv run diff-fls-matches --guideline "Rule 10.1" [--context all_rust|safe_rust|both]
```

**Output:**
```
=== FLS Match Diff: Rule 10.1 ===

FLAGS: applicability_differs_from_add6, fls_removed, rationale_type_changed

--- all_rust ---

MAPPING (v2.1):
  Applicability: yes
  Adjusted Category: required
  Rationale: direct_mapping
  Matches (2):
    - fls_abc123: Arithmetic Expressions (score: 0.65)
      Reason: "Maps to essential type arithmetic"
    - fls_def456: Type Coercion (score: 0.58)
      Reason: "Covers type conversions"

DECISION (v3.1):
  Applicability: no
  Adjusted Category: n_a
  Rationale: no_equivalent
  Analysis Summary:
    MISRA Concern: "..."
    Rust Analysis: "..."
  Matches (2):
    - fls_abc123: Arithmetic Expressions (score: 0.662)
      Reason: "Arithmetic requires same-type operands..."
    - fls_xyz789: Integer Types (score: 0.55)
      Reason: "Defines integer type semantics..."

ADD-6 Reference:
  applicability_all_rust: Yes
  adjusted_category: required
  *** Decision DIFFERS from ADD-6 ***

CHANGES:
  Applicability: yes → no (CHANGED, differs from ADD-6)
  Adjusted Category: required → n_a (CHANGED)
  Rationale Type: direct_mapping → no_equivalent (CHANGED)

  + ADDED: fls_xyz789 (Integer Types)
  - REMOVED: fls_def456 (Type Coercion)
  = RETAINED: fls_abc123 (Arithmetic Expressions)
```

---

### 5. `generate-analysis-reports`

**Purpose:** Generate Markdown reports synthesizing three layers of data:
1. **Comparison data** - Raw diffs (flags, FLS added/removed)
2. **Outlier analysis** - LLM verdicts and reasoning
3. **Human review** - Accept/reject decisions

**Command:**
```bash
uv run generate-analysis-reports --standard misra-c --batches 1,2,3 [--output-dir cache/analysis/reports/]
```

**Outputs:**

- `combined_report.md` - Full report with all sections
- `final_report.md` - Executive summary
- `batch{N}_report.md` - Per-batch details
- `cross_batch_report.md` - Systematic patterns

**Report Timing:** Reports can be generated at any stage:
- During LLM analysis - shows what's analyzed vs awaiting
- During human review - shows what needs attention
- After completion - documents final state

#### `combined_report.md` - Full Report

Contains all sections:

1. **Executive Summary** - Counts of outliers, analyzed, reviewed
2. **Needs Attention** - Guidelines sorted by priority score (higher = needs more attention)
3. **By Flag Type** - Guidelines grouped by flag with LLM verdicts
4. **Awaiting Analysis** - Guidelines with comparison data but no LLM analysis
5. **Fully Reviewed** - Guidelines where human completed review
6. **Batch Summaries** - Per-batch stats

**Priority scoring** considers:
- `specificity_decreased`: +10 (lost paragraph-level matches)
- `multi_dimension_outlier`: +8 (multiple flags)
- `rationale_type_changed`: +5
- `fls_removed`: +4
- `applicability_differs_from_add6`: +4
- LLM verdict "inappropriate": +10, "needs_review": +7
- Human fully reviewed: -15 (reduces priority)

#### `final_report.md` - Executive Summary

```markdown
# Verification Comparison Analysis - Final Report

Generated: 2026-01-08T12:00:00Z

## Overview

**Total outliers:** 145
**LLM analyzed:** 145 (100%)
**Human reviewed:** 120 (83%)

### Batch Summary

| Batch | Name | Total | Analyzed | Reviewed |
|-------|------|-------|----------|----------|
| 1 | High-score direct | 20 | 20 | 18 |
| 2 | Not applicable | 118 | 118 | 98 |
| 3 | Stdlib & Resources | 7 | 7 | 4 |

### LLM Recommendations

| Recommendation | Count | % |
|----------------|-------|---|
| appropriate | 95 | 66% |
| needs_review | 40 | 28% |
| inappropriate | 10 | 7% |

### Flag Distribution

| Flag | Count |
|------|-------|
| fls_removed | 120 |
| fls_added | 85 |
| specificity_decreased | 45 |
...
```

#### `batch{N}_report.md` - Per-Batch Detail

```markdown
# Batch 2 Report: Not applicable

Generated: 2026-01-08T12:00:00Z

## Summary

**Total guidelines:** 118
**LLM analyzed:** 118
**Human reviewed:** 98

## Guidelines

| Guideline | Score | LLM Verdict | Human Status | Top Flags |
|-----------|-------|-------------|--------------|-----------|
| Rule 10.1 | 29 | needs_review | pending | fls_removed, fls_added, specificity... |
| Rule 10.2 | 29 | appropriate | fully_reviewed | fls_removed, fls_added... |
| Dir 4.6 | 15 | appropriate | fully_reviewed | fls_removed |
| ... | ... | ... | ... | ... |

## LLM Analysis Details

### Rule 10.1

**Recommendation:** needs_review
**Summary:** MISRA essential type model has no Rust equivalent. The removal of generic Type Coercion FLS sections is appropriate, but the addition of Arithmetic Expressions needs justification.

- **categorization:** appropriate - applicability=no is correct
- **fls_removals:** appropriate - removed overly generic sections
- **fls_additions:** needs_review - addition of fls_xyz may be too broad
- **specificity:** inappropriate - lost 2 paragraph-level matches

### Dir 4.6

**Recommendation:** appropriate
**Summary:** Decision correctly marks this as not applicable to Rust. FLS changes are systematic pattern.

- **categorization:** appropriate
- **fls_removals:** appropriate - generic section removal pattern
- **fls_additions:** n_a - no additions
```

#### `cross_batch_report.md` - Cross-Batch Patterns

```markdown
# Cross-Batch Analysis Report

Generated: 2026-01-08T12:00:00Z

**Batches analyzed:** 1, 2, 3
**Total guidelines:** 145

## Systematic FLS Removals

FLS sections removed across multiple guidelines:

| FLS ID | Count | Guidelines |
|--------|-------|------------|
| fls_xyz123 | 18 | Rule 10.1, Rule 10.2, Dir 4.6, ... |
| fls_abc789 | 8 | Rule 5.1, Rule 5.2, ... |

## Systematic FLS Additions

FLS sections added across multiple guidelines:

| FLS ID | Count | Guidelines |
|--------|-------|------------|
| fls_abc456 | 12 | Rule 19.1, Rule 19.2, ... |
| fls_def789 | 5 | Rule 21.3, Rule 21.5, ... |

## Multi-Dimension Outliers

Guidelines with multiple flags set:

| Guideline | Batch | Score | Flags |
|-----------|-------|-------|-------|
| Dir 4.3 | 1 | 53 | applicability_differs_from_add6, adjusted_category_differs... (+3) |
| Rule 10.1 | 2 | 29 | fls_removed, fls_added, specificity_decreased |
| ... | ... | ... | ... |

### By Rationale Code
| Code | Diverges | Total | Rate |
|------|----------|-------|------|
| UB | 5 | 80 | 6% |
| IDB | 2 | 40 | 5% |
| CQ | 2 | 25 | 8% |

## Quality Trajectory

### v3.0 vs v3.1 Decisions

| Metric | v3.0 (Batch 1) | v3.1 (Batch 2-3) |
|--------|----------------|------------------|
| Count | 20 | 125 |
| Has analysis_summary | 0% | 100% |
| Has rejected_matches | 75% | 88% |
| Avg accepted matches | 2.5 | 3.1 |

## Findings

1. **Type Coercion over-matching:** Original automated pipeline over-matched on fls_xyz123
2. **Batch 2 refinement needed:** 8 guidelines don't match "not applicable" pattern
3. **Chapter 10 divergence:** High ADD-6 divergence rate due to C essential type model
```

---

### 6. `review-outliers` (Interactive Human Review)

**Purpose:** Present outliers one-by-one to human reviewer for granular resolution of each flagged aspect, with per-context decisions for FLS changes.

#### Design Principles

1. **Per-context decisions**: All FLS removal/addition decisions are made separately for `all_rust` and `safe_rust` contexts
2. **LLM rationale displayed**: Human sees the LLM's reasoning before making each decision
3. **Explicit decisions required**: Application fails if any context decision is missing
4. **Two modes**: Interactive (prompted) and CLI-flag (bulk/scripted)

#### Command Modes

**Interactive mode (default):**
```bash
uv run review-outliers --standard misra-c [--batch N] [--start-from "Rule X.Y"]
```
Presents each outlier with LLM analysis, prompts for decisions on each aspect.

**Show mode (inspect before deciding):**
```bash
uv run review-outliers --standard misra-c --guideline "Dir 4.3" --show
```
Displays the full LLM analysis with verdicts and per-FLS-ID justifications without prompting for decisions. Useful for inspecting before making CLI-flag decisions.

**CLI-flag mode (for targeted/scripted decisions):**
```bash
# Per-guideline decisions with per-context control
uv run review-outliers --standard misra-c --guideline "Rule 10.1" \
    --accept-categorization \
    --accept-removal fls_xyz123 --context all_rust \
    --reject-removal fls_xyz123 --context safe_rust \
    --reason "Keep in safe_rust for borrow checker reference"

# Accept/reject for both contexts at once
uv run review-outliers --standard misra-c --guideline "Rule 10.1" \
    --accept-addition fls_abc456 --context both

# Bulk rules (apply to all guidelines where this FLS ID appears)
uv run review-outliers --standard misra-c \
    --bulk-accept-removal fls_xyz123 --context both \
    --reason "Over-matched section across all guidelines"

# Bulk rule for one context only
uv run review-outliers --standard misra-c \
    --bulk-accept-removal fls_abc789 --context all_rust \
    --reason "Only relevant in safe_rust context"
```

#### Interactive Flow

The interactive review follows a two-phase approach:

1. **Phase 1: Full Analysis Display** - Show all LLM analysis upfront (same as `--show`)
2. **Phase 2: Per-Aspect Prompting** - Sequentially prompt for each aspect

**Help Feature:** At any prompt, enter `?` to re-display the full analysis.

**Accept All Shortcut:** After the full display, offer `[a]ccept all` to accept all LLM recommendations for the current guideline.

#### Interactive Display Example

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  Outlier Review: Dir 4.3 (1/145)                                             ║
║  Batch: 1 (High-score direct mappings)                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

Flags: specificity_decreased, fls_removed, batch_pattern_outlier

Quick Reference:
  ADD-6: applicability_all_rust=Yes, applicability_safe_rust=Yes
  Decision (all_rust): applicability=yes, rationale_type=direct_mapping
  Decision (safe_rust): applicability=no, rationale_type=rust_prevents

============================================================
LLM ANALYSIS: Dir 4.3
============================================================

Overall Recommendation: accept

Summary:
  MISRA Dir 4.3 requires assembly to be encapsulated. Rust naturally
  satisfies this via asm! macro requirement in unsafe blocks.

--- Categorization ---
  Verdict: appropriate
  Reasoning: The applicability=yes and rationale_type=direct_mapping are
             correct. Rust's asm! macro requirement aligns with MISRA's
             encapsulation intent.

--- FLS Removals ---
  Verdict: inappropriate
  Reasoning: The removed paragraphs are directly relevant legality rules
             about inline assembly - they should be retained.
  Per-ID:
    fls_3fg60jblx0xb (contexts: all_rust):
      Title: Inline Assembly legality
      Category: -2
      Original reason: Per FLS: 'Inline assembly is written as an assembly
                       code block that is wrapped inside a macro invocation'
      LLM justification (all_rust): This legality rule is directly relevant -
                                     should not be removed

    fls_4lb6yh12w1cv (contexts: all_rust):
      Title: asm macro invocation
      Category: -2
      Original reason: Per FLS: 'Invoking macro core::arch::asm causes...'
      LLM justification (all_rust): Directly relevant - should not be removed

--- Specificity ---
  Verdict: inappropriate
  Reasoning: Lost 2 paragraph-level legality rules about inline assembly
  Lost paragraphs:
    - fls_3fg60jblx0xb (Inline Assembly legality)
    - fls_4lb6yh12w1cv (asm macro invocation)

--- ADD-6 Divergence ---
  Verdict: n_a
  Reasoning: Decision matches ADD-6 applicability

============================================================

[a]ccept all | [r]eview each | [s]kip | [q]uit > r

══════════════════════════════════════════════════════════════════════════════
CATEGORIZATION
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: appropriate
LLM Reasoning: The applicability=yes and rationale_type=direct_mapping are
               correct. Rust's asm! macro requirement aligns with MISRA's
               encapsulation intent.

  all_rust:  applicability no change, rationale no change
  safe_rust: applicability no change, rationale no change

Accept categorization? [y]es | [n]o | [s]kip | [?] help | [q]uit > y

══════════════════════════════════════════════════════════════════════════════
FLS REMOVALS (2 items)
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: inappropriate
LLM Reasoning: The removed paragraphs are directly relevant legality rules
               about inline assembly - they should be retained.

  [1/2] fls_3fg60jblx0xb: Inline Assembly legality (category: -2)
        Contexts: all_rust
        Original reason: Per FLS: 'Inline assembly is written as an assembly
                         code block that is wrapped inside a macro invocation'
        LLM justification (all_rust): This legality rule is directly relevant -
                                       should not be removed

        Accept removal for all_rust? [y]es | [n]o | [?] help > n

  [2/2] fls_4lb6yh12w1cv: asm macro invocation (category: -2)
        Contexts: all_rust
        Original reason: Per FLS: 'Invoking macro core::arch::asm causes...'
        LLM justification (all_rust): Directly relevant - should not be removed

        Accept removal for all_rust? [y]es | [n]o | [?] help > n

══════════════════════════════════════════════════════════════════════════════
SPECIFICITY
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: inappropriate
LLM Reasoning: Lost 2 paragraph-level legality rules about inline assembly
               that should be restored.

Lost paragraphs:
  - fls_3fg60jblx0xb (category -2): Inline Assembly legality
  - fls_4lb6yh12w1cv (category -2): asm macro invocation

Accept specificity loss? [y]es | [n]o | [s]kip | [?] help > n

══════════════════════════════════════════════════════════════════════════════
ADD-6 DIVERGENCE
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: justified
LLM Reasoning: safe_rust applicability is no because asm! macro requires
               unsafe context (FLS fls_s5nfhBFOk8Bu). ADD-6 says Yes which
               appears incorrect for safe Rust.

ADD-6 Reference:
  applicability_all_rust: Yes
  applicability_safe_rust: Yes
  adjusted_category: advisory

Per-context divergence:
  all_rust: ADD-6=Yes, Decision=(unchanged) ✓
  safe_rust: ADD-6=Yes, Decision=(unchanged) ✗ DIVERGES

Accept divergence from ADD-6? [y]es | [n]o | [s]kip | [?] help > y

══════════════════════════════════════════════════════════════════════════════

✓ Dir 4.3 review complete
  Categorization: accepted
  FLS Removals:
    fls_3fg60jblx0xb: all_rust=reject
    fls_4lb6yh12w1cv: all_rust=reject
  Specificity: rejected
  ADD-6 Divergence: accepted

Press Enter to continue to next outlier...
```

#### Context Display at Each Prompt (Enhanced)

**Problem identified (2026-01-09):** The original design only showed minimal context at each per-aspect prompt. For example, at the categorization prompt:

```
══════════════════════════════════════════════════════════════════════════════
CATEGORIZATION
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: appropriate

  all_rust:  applicability no change, rationale no change
  safe_rust: applicability no change, rationale no change

Accept categorization? [y]es | [n]o | [s]kip | [?] help | [q]uit > 
```

This lacks the **LLM reasoning** which is critical for informed decisions.

**Solution:** Each per-aspect section MUST display:

| Aspect | Must Display |
|--------|--------------|
| Categorization | LLM verdict + **full reasoning** + per-context changes |
| FLS Removals | LLM verdict + **full overall reasoning** + per-ID: title, category, **full original reason**, LLM justification |
| FLS Additions | LLM verdict + **full overall reasoning** + per-ID: title, category, **full new reason**, LLM justification |
| Specificity | LLM verdict + **full reasoning** + complete lost paragraphs list |
| ADD-6 Divergence | LLM verdict + **full reasoning** + ADD-6 reference values + per-context divergence |

**No truncation at decision prompts:** Unlike the overview display (`display_llm_analysis()` which truncates for brevity), the per-aspect prompts must show **complete, untruncated content**. The human reviewer needs the full FLS quotes and reasoning to make informed accept/reject decisions. Long content will naturally wrap in the terminal.

The `[?] help` option remains available to re-display the full analysis overview, but the key reasoning for the current aspect should always be visible in full without needing to press `?`.

#### Per-Context Categorization Review

**Problem identified (2026-01-09):** The original CATEGORIZATION prompt treated both contexts as a single decision:

```
══════════════════════════════════════════════════════════════════════════════
CATEGORIZATION
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: appropriate

  all_rust: applicability no change, rationale no change
  safe_rust: applicability no change, rationale no change

Accept categorization? [y]es | [n]o | [s]kip | [?] help | [q]uit >
```

**Issues:**
1. Shows "no change" without showing what the actual values are
2. Doesn't show whether those values diverge from ADD-6
3. Records a single decision for both contexts when they may need different decisions
4. Reviewer cannot accept one context and reject the other

**Solution:** Categorization must be reviewed per-context, showing:
- Actual applicability value (yes/no/partial)
- Actual rationale_type value (direct_mapping/rust_prevents/etc.)
- Actual adjusted_category value (advisory/required/etc.)
- ADD-6 expected values and divergence status
- Separate accept/reject decision for each context

**Enhanced CATEGORIZATION display:**

```
══════════════════════════════════════════════════════════════════════════════
CATEGORIZATION
══════════════════════════════════════════════════════════════════════════════
LLM Verdict: appropriate
LLM Reasoning: applicability=yes and rationale_type=direct_mapping correct 
               for all_rust - Rust asm! macro encapsulates assembly

─────────────────────────────────────────────────────────────────────────────
Context: all_rust
─────────────────────────────────────────────────────────────────────────────
  Applicability:      yes (no change from mapping)
  Rationale type:     direct_mapping (no change from mapping)
  Adjusted category:  advisory (no change from mapping)
  
  ADD-6 Reference:
    Applicability:    Yes ✓ (matches)
    Adjusted category: advisory ✓ (matches)

Accept all_rust categorization? [y]es | [n]o | [s]kip | [i]nvestigate | [?] help | [q]uit > y

─────────────────────────────────────────────────────────────────────────────
Context: safe_rust
─────────────────────────────────────────────────────────────────────────────
  Applicability:      no (no change from mapping)
  Rationale type:     rust_prevents (no change from mapping)
  Adjusted category:  n_a (no change from mapping)
  
  ADD-6 Reference:
    Applicability:    Yes ✗ DIVERGES (decision says 'no', ADD-6 says 'Yes')
    Adjusted category: advisory ✗ DIVERGES (decision says 'n_a', ADD-6 says 'advisory')

Accept safe_rust categorization? [y]es | [n]o | [s]kip | [i]nvestigate | [?] help | [q]uit > y
```

**Data requirements:** The outlier_analysis file must include context metadata from the comparison_data:
- `context_metadata.all_rust.{applicability, rationale_type, adjusted_category}` (from decision)
- `context_metadata.safe_rust.{applicability, rationale_type, adjusted_category}` (from decision)
- `context_metadata.mapping.all_rust.{applicability, rationale_type, adjusted_category}` (from mapping)
- `context_metadata.mapping.safe_rust.{applicability, rationale_type, adjusted_category}` (from mapping)

This data is already extracted in comparison_data files - record.py needs to copy it to outlier_analysis files.

**human_review structure change:** The `categorization` field must store per-context decisions:

```json
"human_review": {
  "categorization": {
    "all_rust": {"decision": "accept", "reason": null},
    "safe_rust": {"decision": "accept", "reason": null}
  },
  ...
}
```

#### Per-Context Categorization in record-outlier-analysis

**Problem:** The `record-outlier-analysis` tool originally accepted a single `--categorization-verdict` and `--categorization-reasoning` for the entire guideline. But since the two contexts (all_rust, safe_rust) can have very different characteristics - one might be applicable while the other is not - the LLM analysis should provide per-context verdicts.

**Solution:** Update `record-outlier-analysis` to accept per-context categorization:

**Old CLI (single verdict):**
```bash
uv run record-outlier-analysis \
    --categorization-verdict appropriate \
    --categorization-reasoning "Both contexts correctly categorized"
```

**New CLI (per-context verdicts):**
```bash
uv run record-outlier-analysis \
    --categorization-verdict-all-rust appropriate \
    --categorization-reasoning-all-rust "applicability=yes, rationale_type=direct_mapping correct for Rust asm! encapsulation" \
    --categorization-verdict-safe-rust appropriate \
    --categorization-reasoning-safe-rust "applicability=no correct - asm! requires unsafe context, ADD-6 divergence is justified"
```

**New CLI options:**
- `--categorization-verdict-all-rust {appropriate,inappropriate,needs_review,n_a}`
- `--categorization-reasoning-all-rust TEXT`
- `--categorization-verdict-safe-rust {appropriate,inappropriate,needs_review,n_a}`
- `--categorization-reasoning-safe-rust TEXT`

**llm_analysis structure change:**

```json
"llm_analysis": {
  "categorization": {
    "all_rust": {
      "verdict": "appropriate",
      "reasoning": "applicability=yes, rationale_type=direct_mapping correct..."
    },
    "safe_rust": {
      "verdict": "appropriate", 
      "reasoning": "applicability=no correct - asm! requires unsafe..."
    }
  },
  ...
}
```

**Review tool display change:** The review tool should show the per-context LLM verdict alongside each context section:

```
──────────────────────────────────────────────────────────────────────────────
Context: all_rust
──────────────────────────────────────────────────────────────────────────────
LLM Verdict: appropriate
LLM Reasoning: applicability=yes, rationale_type=direct_mapping correct...

  Applicability:      yes (no change from mapping)
  ...
```

#### Per-Context Acknowledgment Requirements

**Problem identified (2026-01-09):** The original outlier analysis approach allowed lazy LLM analysis. An LLM could generate analysis without explicitly addressing:
1. **Mapping → Decision changes** - Changes detected in the comparison data
2. **Decision → ADD-6 divergence** - Divergence from MISRA ADD-6 official applicability

Without forced acknowledgment, the LLM might produce shallow analysis that misses important changes or divergences.

**Solution:** Require explicit acknowledgment of every flagged change/divergence in the `record-outlier-analysis` tool.

##### What Must Be Acknowledged

For each context (all_rust, safe_rust), the LLM must acknowledge:

| Category | When Required | Source Flag |
|----------|---------------|-------------|
| Applicability change from mapping | If `comparison.{ctx}.applicability_changed == true` | `flags.rationale_type_changed` |
| Rationale type change from mapping | If `comparison.{ctx}.rationale_type_changed == true` | `flags.rationale_type_changed` |
| Adjusted category change from mapping | If `comparison.{ctx}.adjusted_category_changed == true` | `flags.adjusted_category_differs_from_add6` |
| Applicability diverges from ADD-6 | If `comparison.{ctx}.applicability_differs_from_add6 == true` | `flags.applicability_differs_from_add6` |
| Adjusted category diverges from ADD-6 | If `comparison.{ctx}.adjusted_category_differs_from_add6 == true` | `flags.adjusted_category_differs_from_add6` |

##### New CLI Flags for record-outlier-analysis

**Change acknowledgment flags (mapping → decision):**
```bash
--cat-ack-change-applicability-all-rust "Acknowledgment text..."
--cat-ack-change-applicability-safe-rust "Acknowledgment text..."
--cat-ack-change-rationale-all-rust "Acknowledgment text..."
--cat-ack-change-rationale-safe-rust "Acknowledgment text..."
--cat-ack-change-category-all-rust "Acknowledgment text..."
--cat-ack-change-category-safe-rust "Acknowledgment text..."
```

**Divergence acknowledgment flags (decision → ADD-6):**
```bash
--cat-ack-diverge-applicability-all-rust "Acknowledgment text..."
--cat-ack-diverge-applicability-safe-rust "Acknowledgment text..."
--cat-ack-diverge-category-all-rust "Acknowledgment text..."
--cat-ack-diverge-category-safe-rust "Acknowledgment text..."
```

##### Validation Rules

1. **Required when flagged:** If a change/divergence is flagged in comparison data, the corresponding acknowledgment MUST be provided
2. **Minimum length:** Each acknowledgment must be ≥20 characters (prevents lazy "same" or "OK" responses)
3. **Cross-validation:** The actual values provided in acknowledgments must reference what's in comparison_data
4. **No shared reasoning:** If both contexts have identical reasoning, the reasoning must explicitly note this (e.g., "Same rationale applies to both contexts because...")

##### Updated llm_analysis.categorization Structure

```json
"llm_analysis": {
  "categorization": {
    "all_rust": {
      "actual_values": {
        "applicability": "no",
        "rationale_type": "no_equivalent",
        "adjusted_category": "n_a"
      },
      "changes_from_mapping": {
        "applicability": { "from": "yes", "to": "no" },
        "rationale_type": { "from": "direct_mapping", "to": "no_equivalent" },
        "adjusted_category": null
      },
      "diverges_from_add6": {
        "applicability": { "decision": "no", "add6": "Yes" },
        "adjusted_category": null
      },
      "verdict": "appropriate",
      "reasoning": "The overall categorization is appropriate...",
      "change_acknowledgments": {
        "applicability": "Changed from yes to no because Rust has no equivalent to X...",
        "rationale_type": "Changed from direct_mapping to no_equivalent because..."
      },
      "divergence_acknowledgments": {
        "applicability": "Diverges from ADD-6=Yes because safe Rust cannot access..."
      }
    },
    "safe_rust": {
      // Same structure
    }
  }
}
```

##### Example: Dir 4.3 with Full Acknowledgments

**Comparison data shows:**
- `all_rust`: No changes, no divergence
- `safe_rust`: applicability_differs_from_add6=true (decision=no, ADD-6=Yes)

**Required CLI flags:**
```bash
uv run record-outlier-analysis --standard misra-c --guideline "Dir 4.3" --batch 1 \
    --analysis-summary "MISRA Dir 4.3 requires assembly encapsulation..." \
    --categorization-verdict-all-rust appropriate \
    --categorization-reasoning-all-rust "applicability=yes correct - asm! macro provides encapsulation" \
    --categorization-verdict-safe-rust appropriate \
    --categorization-reasoning-safe-rust "applicability=no correct - asm! requires unsafe context" \
    --cat-ack-diverge-applicability-safe-rust "ADD-6 says Yes but asm! requires unsafe per FLS fls_s5nfhBFOk8Bu. Safe Rust cannot use asm!, so applicability must be no." \
    ... (other flags)
```

**Note:** `--cat-ack-diverge-applicability-all-rust` is NOT required because `all_rust` does not diverge from ADD-6.

##### Validation Failure Example

```
ERROR: Dir 4.3 has validation errors:
  - Missing --cat-ack-diverge-applicability-safe-rust (required: comparison.safe_rust.applicability_differs_from_add6 is true)
```

##### Why This Matters

1. **Forces thorough analysis:** LLM cannot skip over flagged items
2. **Creates audit trail:** Each divergence/change has explicit justification
3. **Enables human review:** Reviewer sees exactly what was acknowledged and why
4. **Prevents lazy patterns:** Short or templated responses are rejected

#### Prompt Options

| Key | Meaning |
|-----|---------|
| `y` | Accept this aspect/decision |
| `n` | Reject this aspect/decision |
| `s` | Skip (leave undecided for now) |
| `a` | Accept all remaining aspects for this guideline |
| `?` | Re-display full LLM analysis |
| `q` | Quit and show resume command |

#### Per-Context Decision Structure

FLS removal and addition decisions are stored **per-FLS-ID** with a `contexts` array and `decisions` dict keyed by context:

```json
"human_review": {
  "reviewed_at": "2026-01-08T14:30:00Z",
  "overall_status": "fully_reviewed",
  "categorization": {
    "decision": "accept",
    "reason": "Categorization is correct"
  },
  "fls_removals": {
    "fls_3fg60jblx0xb": {
      "title": "Inline Assembly legality",
      "category": -2,
      "contexts": ["all_rust"],
      "decisions": {
        "all_rust": { "decision": "reject", "reason": "Keep - directly relevant legality rule" }
      }
    },
    "fls_4lb6yh12w1cv": {
      "title": "asm macro invocation",
      "category": -2,
      "contexts": ["all_rust"],
      "decisions": {
        "all_rust": { "decision": "reject", "reason": "Keep - asm macro invocation rule" }
      }
    }
  },
  "fls_additions": {
    "fls_s5nfhBFOk8Bu": {
      "title": "Unsafety legality rule",
      "category": -2,
      "contexts": ["all_rust", "safe_rust"],
      "decisions": {
        "all_rust": { "decision": "accept", "reason": "Unsafety legality is relevant" },
        "safe_rust": { "decision": "accept", "reason": null }
      }
    }
  },
  "specificity": {
    "decision": "reject",
    "reason": "Restore lost paragraph-level matches"
  },
  "add6_divergence": {
    "decision": "accept",
    "reason": "Divergence is intentional based on Rust semantics"
  },
  "notes": null
}
```

**Key points:**
- `categorization`, `specificity`, and `add6_divergence` are single decisions (not per-context)
- `fls_removals` and `fls_additions` store per-FLS-ID with `contexts` array and `decisions` dict
- `decisions` dict is keyed by context name, only includes contexts where the FLS ID appears
- Human must decide for each context where an FLS ID appears

#### Decision Values

| Decision | Meaning |
|----------|---------|
| `accept` | Accept the LLM's decision for this aspect/context |
| `reject` | Reject the LLM's decision (keep/restore original state) |
| `n_a` | Not applicable (FLS ID not present in this context) |

#### Validation Rules

**Application fails if:**
1. Any FLS removal/addition is missing a decision for a context where it applies
2. Categorization is missing a decision for either context
3. Specificity decision is missing when `specificity_decreased` flag is set
4. ADD-6 divergence decision is missing when divergence flags are set

**Context applicability:**
- An FLS ID may only exist in one context (e.g., only in `all_rust`)
- For such IDs, the other context should have `decision: "n_a"`
- The tool determines which contexts need decisions based on comparison data

#### Bulk Rules

Bulk rules can specify context:

```json
{
  "bulk_rules": {
    "accept_removals": {
      "fls_xyz123": { "all_rust": true, "safe_rust": true },
      "fls_abc789": { "all_rust": true, "safe_rust": false }
    },
    "accept_additions": {
      "fls_def456": { "all_rust": true, "safe_rust": true }
    },
    "notes": "fls_xyz123 was over-matched by automated pipeline"
  }
}
```

#### `review_state.json` Structure

```json
{
  "last_updated": "2026-01-08T14:30:00Z",
  "bulk_rules": {
    "accept_removals": {
      "fls_xyz123": { "all_rust": true, "safe_rust": true }
    },
    "accept_additions": {},
    "notes": "fls_xyz123 was over-matched by automated pipeline"
  },
  "summary": {
    "total_outliers": 145,
    "fully_reviewed": 32,
    "partially_reviewed": 5,
    "pending": 108,
    "by_aspect": {
      "categorization": {
        "all_rust": { "accepted": 30, "rejected": 2, "pending": 113 },
        "safe_rust": { "accepted": 28, "rejected": 4, "pending": 113 }
      },
      "fls_removals": {
        "all_rust": { "accepted": 45, "rejected": 3, "pending": 94 },
        "safe_rust": { "accepted": 40, "rejected": 5, "pending": 97 }
      },
      "fls_additions": {
        "all_rust": { "accepted": 28, "rejected": 1, "pending": 113 },
        "safe_rust": { "accepted": 25, "rejected": 3, "pending": 114 }
      },
      "specificity": { "accepted": 10, "rejected": 5, "pending": 32 },
      "add6_divergence": {
        "all_rust": { "accepted": 8, "rejected": 1, "pending": 0 },
        "safe_rust": { "accepted": 6, "rejected": 2, "pending": 1 }
      }
    }
  }
}
```

#### Overall Status Computation

```python
def compute_overall_status(human_review: dict, flags: dict, comparison: dict) -> str:
    """
    Compute review status. Returns 'fully_reviewed', 'partial', or 'pending'.
    
    All applicable contexts must have explicit decisions.
    """
    pending_count = 0
    total_count = 0
    
    # Categorization (always required for both contexts)
    for ctx in ["all_rust", "safe_rust"]:
        total_count += 1
        cat = human_review.get("categorization", {}).get(ctx, {})
        if not cat.get("decision"):
            pending_count += 1
    
    # FLS removals (per-context, only where applicable)
    for fls_id, contexts in human_review.get("fls_removals", {}).items():
        for ctx in ["all_rust", "safe_rust"]:
            # Check if this FLS was removed in this context
            if fls_id in comparison.get(ctx, {}).get("fls_removed", []):
                total_count += 1
                if not contexts.get(ctx, {}).get("decision"):
                    pending_count += 1
    
    # FLS additions (per-context, only where applicable)
    for fls_id, contexts in human_review.get("fls_additions", {}).items():
        for ctx in ["all_rust", "safe_rust"]:
            if fls_id in comparison.get(ctx, {}).get("fls_added", []):
                total_count += 1
                if not contexts.get(ctx, {}).get("decision"):
                    pending_count += 1
    
    # Specificity (if flag set)
    if flags.get("specificity_decreased"):
        total_count += 1
        if not human_review.get("specificity", {}).get("decision"):
            pending_count += 1
    
    # ADD-6 divergence (per-context, if flags set)
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        for ctx in ["all_rust", "safe_rust"]:
            total_count += 1
            add6 = human_review.get("add6_divergence", {}).get(ctx, {})
            if not add6.get("decision"):
                pending_count += 1
    
    if pending_count == 0:
        return "fully_reviewed"
    elif pending_count < total_count:
        return "partial"
    else:
        return "pending"
```

---

### 6b. LLM-Assisted Review Mode (OpenCode Integration)

**Purpose:** Enable human reviewers to request LLM investigation during interactive review, with findings recorded to the outlier analysis file for informed decision-making. Integrates with OpenCode via a skill and CLI tool.

#### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Human runs review tool inside OpenCode TUI                                  │
│  > uv run review-outliers --standard misra-c --batch 1                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Interactive review displays guideline analysis                              │
│                                                                              │
│  Accept removal for all_rust? [y]es | [n]o | [i]nvestigate | [?] help >     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            [y/n/s/q]                    [i] or [i "guidance..."]
            Normal flow                              │
                                                     ▼
                                    ┌─────────────────────────────────────────┐
                                    │  review-outliers outputs:               │
                                    │  INVESTIGATION_REQUEST:{...json...}     │
                                    │                                         │
                                    │  Then waits for Enter                   │
                                    └─────────────────────────────────────────┘
                                                     │
                                                     ▼
                                    ┌─────────────────────────────────────────┐
                                    │  OpenCode LLM (via skill) sees request: │
                                    │  1. Loads outlier-review skill          │
                                    │  2. Reads FLS content, MISRA rationale  │
                                    │  3. Considers user_guidance if provided │
                                    │  4. Calls record-investigation tool     │
                                    │  5. Reports findings to user            │
                                    └─────────────────────────────────────────┘
                                                     │
                                                     ▼
                                    ┌─────────────────────────────────────────┐
                                    │  User presses Enter in review tool      │
                                    │  Tool reloads outlier file              │
                                    │  Displays investigation findings        │
                                    │  Re-prompts for decision                │
                                    └─────────────────────────────────────────┘
```

#### Investigation Input Syntax

The `[i]nvestigate` option accepts optional natural language guidance:

| Input | Effect |
|-------|--------|
| `i` | Investigate current aspect with no additional guidance |
| `i "guidance text"` | Investigate with user-provided context/instructions |

**Examples:**

```
# Simple investigation
Accept removal for all_rust? [y]es | [n]o | [i]nvestigate | [?] help > i

# Investigation with guidance  
Accept removal for all_rust? [y]es | [n]o | [i]nvestigate | [?] help > i "I reread MISRA Dir 4.3 - it's about encapsulation not safety. Check if asm! macro satisfies the encapsulation requirement."

# Investigation with domain knowledge
Accept ADD-6 divergence? [y]es | [n]o | [i]nvestigate | [?] help > i "ADD-6 says Yes for safe_rust but asm! requires unsafe. Verify this is actually a divergence."
```

#### Investigation Request Format

When user triggers investigation, the review tool outputs:

```
INVESTIGATION_REQUEST:{"guideline_id":"Dir 4.3","aspect":"fls_removal","fls_id":"fls_3fg60jblx0xb","context":"all_rust","user_guidance":"I reread MISRA Dir 4.3 - it's about encapsulation..."}

Investigation requested. Perform investigation and press Enter when complete...
(Or press 'c' then Enter to cancel)
```

**JSON fields:**

| Field | Type | Description |
|-------|------|-------------|
| `guideline_id` | string | The MISRA guideline being reviewed |
| `aspect` | string | One of: `fls_removal`, `fls_addition`, `categorization`, `specificity`, `add6_divergence`, `all` |
| `fls_id` | string? | FLS ID for FLS-specific investigations |
| `context` | string? | `all_rust` or `safe_rust` for context-specific investigations |
| `user_guidance` | string? | Optional natural language guidance from user |

#### OpenCode Skill: `outlier-review`

**Location:** `.opencode/skill/outlier-review/SKILL.md`

**Purpose:** Teaches the LLM how to handle `INVESTIGATION_REQUEST` markers and conduct investigations.

**Skill responsibilities:**
1. Watch for `INVESTIGATION_REQUEST:` in tool output
2. Parse the JSON request
3. Read relevant source files (FLS chapters, MISRA text, outlier file)
4. Consider `user_guidance` if provided
5. Call `record-investigation` tool to persist findings
6. Report findings to the user
7. Instruct user to press Enter to continue the review tool

#### CLI Tool: `record-investigation`

**Purpose:** Record investigation findings to an outlier analysis file in a structured format.

**Command:**
```bash
uv run record-investigation \
    --standard misra-c \
    --guideline "Dir 4.3" \
    --aspect fls_removal \
    --fls-id fls_3fg60jblx0xb \
    --context all_rust \
    --source "embeddings/fls/chapter_22.json" \
    --source "cache/misra_c_extracted_text.json" \
    --fls-content "Inline assembly is written as an assembly code block..." \
    --relevance "This legality rule directly addresses MISRA Dir 4.3's requirement" \
    --recommendation "KEEP" \
    --confidence high \
    --user-guidance "User noted: encapsulation is the key concern"
```

**Required parameters:**

| Parameter | Description |
|-----------|-------------|
| `--standard` | Standard (misra-c, etc.) |
| `--guideline` | Guideline ID (e.g., "Dir 4.3") |
| `--aspect` | Aspect type being investigated |
| `--relevance` | Assessment of relevance to MISRA concern |
| `--recommendation` | Recommended action (KEEP, REMOVE, ACCEPT, etc.) |
| `--confidence` | Confidence level (high, medium, low) |

**Optional parameters:**

| Parameter | Description |
|-----------|-------------|
| `--fls-id` | FLS ID (for FLS-specific aspects) |
| `--context` | Context (all_rust, safe_rust) |
| `--source` | Source file consulted (can repeat) |
| `--fls-content` | Summary of FLS content examined |
| `--user-guidance` | User's guidance that informed investigation |
| `--notes` | Additional notes |

**Output:** Updates the outlier file's `llm_investigation.investigations` array.

#### Investigation Data Structure

```json
{
  "guideline_id": "Dir 4.3",
  "llm_analysis": { ... },
  "llm_investigation": {
    "investigations": [
      {
        "timestamp": "2026-01-09T15:30:00Z",
        "aspect": "fls_removal",
        "target": {
          "fls_id": "fls_3fg60jblx0xb",
          "context": "all_rust"
        },
        "trigger": "human_request",
        "user_guidance": "I reread MISRA Dir 4.3 - it's about encapsulation...",
        "sources_consulted": [
          "embeddings/fls/chapter_22.json (Inline Assembly)",
          "embeddings/fls/chapter_19.json (Unsafety)",
          "cache/misra_c_extracted_text.json (Dir 4.3)"
        ],
        "findings": {
          "fls_content_summary": "FLS fls_3fg60jblx0xb states: 'Inline assembly is written as an assembly code block that is wrapped inside a macro invocation of macro core::arch::asm, macro core::arch::global_asm, or macro core::arch::naked_asm.'",
          "relevance_assessment": "This legality rule directly addresses MISRA Dir 4.3's requirement that assembly be encapsulated. The FLS mandates macro encapsulation, which satisfies the MISRA intent.",
          "recommendation": "KEEP - This FLS paragraph provides citable normative text for coding guidelines about assembly encapsulation.",
          "confidence": "high"
        }
      }
    ]
  },
  "human_review": { ... }
}
```

#### Complete Workflow Example

1. **User starts review in OpenCode:**
   ```
   > uv run review-outliers --standard misra-c --batch 1
   ```

2. **Review tool displays Dir 4.3 analysis:**
   ```
   ╔══════════════════════════════════════════════════════════════════════════════╗
   ║  Outlier Review: Dir 4.3                                  (1/20)             ║
   ╚══════════════════════════════════════════════════════════════════════════════╝
   
   [... LLM analysis displayed ...]
   
   ══════════════════════════════════════════════════════════════════════════════
   FLS REMOVALS (2 items)
   ══════════════════════════════════════════════════════════════════════════════
   
     [1/2] fls_3fg60jblx0xb: Inline Assembly legality (category: -2)
           LLM justification: KEEP - directly relevant legality rule
   
           Accept removal for all_rust? [y]es | [n]o | [i]nvestigate | [?] help > 
   ```

3. **User requests investigation with guidance:**
   ```
   > i "MISRA Dir 4.3 is about encapsulation of assembly, not safety. Does asm! macro satisfy encapsulation?"
   ```

4. **Review tool outputs request and waits:**
   ```
   INVESTIGATION_REQUEST:{"guideline_id":"Dir 4.3","aspect":"fls_removal","fls_id":"fls_3fg60jblx0xb","context":"all_rust","user_guidance":"MISRA Dir 4.3 is about encapsulation of assembly, not safety. Does asm! macro satisfy encapsulation?"}
   
   Investigation requested. Perform investigation and press Enter when complete...
   (Or press 'c' then Enter to cancel)
   ```

5. **OpenCode LLM (me) sees the request, loads skill, investigates:**
   - Reads FLS chapter 22 (Inline Assembly)
   - Reads MISRA Dir 4.3 rationale
   - Notes user guidance about encapsulation
   - Calls `record-investigation` tool:
     ```bash
     uv run record-investigation --standard misra-c --guideline "Dir 4.3" \
       --aspect fls_removal --fls-id fls_3fg60jblx0xb --context all_rust \
       --source "embeddings/fls/chapter_22.json" \
       --fls-content "asm! macro wraps assembly in a macro invocation, providing syntactic encapsulation" \
       --relevance "Directly satisfies MISRA's encapsulation requirement - assembly must go through asm! macro" \
       --recommendation "KEEP" --confidence high \
       --user-guidance "User noted: encapsulation is the key concern, not safety"
     ```
   - Reports to user: "Investigation complete. The FLS shows asm! provides encapsulation via macro syntax. Press Enter to continue."

6. **User presses Enter, review tool continues:**
   ```
   ────────────────────────────────────────────────────────────────
   INVESTIGATION FINDINGS
   ────────────────────────────────────────────────────────────────
   
   [2026-01-09T15:30:00Z] fls_removal - fls_3fg60jblx0xb (all_rust)
     User guidance: MISRA Dir 4.3 is about encapsulation...
     FLS Content: asm! macro wraps assembly in a macro invocation...
     Relevance: Directly satisfies MISRA's encapsulation requirement
     Recommendation: KEEP (confidence: high)
   ────────────────────────────────────────────────────────────────
   
   Accept removal for all_rust? [y]es | [n]o | [?] help > n
     Decision recorded: reject (keep FLS match)
   ```

#### Implementation Checklist

1. **`review.py` updates:**
   - [ ] Parse `i` with optional quoted string argument
   - [ ] Include `user_guidance` in `INVESTIGATION_REQUEST` JSON
   - [ ] Display investigation findings after reload

2. **`record-investigation` tool:**
   - [ ] Create `tools/src/fls_tools/standards/analysis/record_investigation.py`
   - [ ] Add entry point in `pyproject.toml`
   - [ ] Validate parameters and update outlier file

3. **OpenCode skill:**
   - [ ] Create `.opencode/skill/outlier-review/SKILL.md`
   - [ ] Document how to handle `INVESTIGATION_REQUEST`
   - [ ] Document how to use `record-investigation` tool
   - [ ] Document key file locations

4. **Testing:**
   - [ ] Test `i` without guidance
   - [ ] Test `i "guidance"` with guidance
   - [ ] Test `record-investigation` tool
   - [ ] Test full workflow in OpenCode

#### Implementation Notes

1. **Skill loading:** The OpenCode LLM should load the `outlier-review` skill when it sees `INVESTIGATION_REQUEST:` in output. The skill provides detailed instructions for conducting investigations.

2. **Investigation history:** Keep all investigations in an array - don't overwrite previous investigations. This creates an audit trail.

3. **Graceful degradation:** If investigation fails (file not found, etc.), the LLM should report the error and the user can press Enter to continue without findings.

4. **Control flow:** The review tool maintains control of the interactive loop. The LLM only updates the outlier file; the review tool handles all prompts and decisions.

---

### 7. `apply-verification` (Extended)

**Purpose:** Apply verified decisions to the mapping file, with analysis gate and granular control.

**Command:**
```bash
# Normal usage - requires analysis directory
uv run apply-verification \
    --standard misra-c \
    --batch 1 \
    --session 5 \
    --analysis-dir cache/analysis/

# Escape hatch - skip analysis requirement
uv run apply-verification \
    --standard misra-c \
    --batch 1 \
    --session 5 \
    --skip-analysis-check --force
```

**Behavior with `--analysis-dir`:**
1. Validates analysis directory exists
2. Checks `review_state.json` for completion status
3. **Fails if:**
   - Any outlier has `overall_status: pending` (completely unreviewed)
   - Any outlier has `overall_status: partial` (partially reviewed) - must complete or skip
4. Computes what will actually be applied based on granular decisions
5. Prints detailed summary before proceeding
6. Prompts for confirmation

**Granular Application Logic:**

When applying a guideline's decision, the tool respects granular human decisions:

| Aspect | Human Decision | Effect on Apply |
|--------|----------------|-----------------|
| Categorization | `accept` | Apply new applicability/rationale_type from decision |
| Categorization | `reject` | Keep existing applicability/rationale_type from mapping |
| FLS Removal (specific ID) | `accept` | Removed ID does not appear in final accepted_matches |
| FLS Removal (specific ID) | `reject` | Keep the ID in accepted_matches (from mapping) |
| FLS Addition (specific ID) | `accept` | Added ID appears in final accepted_matches |
| FLS Addition (specific ID) | `reject` | Added ID does not appear in final accepted_matches |
| ADD-6 Divergence | `accept` | Apply decision values even though they differ from ADD-6 |
| ADD-6 Divergence | `reject` | Revert to ADD-6 values for applicability/adjusted_category |

**Validation output:**
```
=== Analysis Validation ===

Review Status:
  Total outliers: 54
  Fully reviewed: 52 (96%)
  Partially reviewed: 0
  Pending: 2

Pending outliers (blocking apply):
  - Rule 10.5: not reviewed
  - Dir 4.12: not reviewed

Run `uv run review-outliers --start-from "Rule 10.5"` to complete review.
```

After all outliers reviewed:

```
=== Analysis Validation ===

Review Status:
  Total outliers: 54
  Fully reviewed: 54 (100%)

Application Summary:

Guidelines with full acceptance (140):
  All aspects of decision will be applied as-is.

Guidelines with partial acceptance (3):
  Rule 10.1:
    ✓ Categorization: accepted (yes→no, direct_mapping→no_equivalent)
    ✓ FLS Removals: 1/1 accepted
    ✗ FLS Additions: 0/2 accepted (fls_xyz789, fls_abc456 rejected)
    ✓ ADD-6 Divergence: accepted
    
  Dir 4.6:
    ✓ Categorization: accepted
    ✗ FLS Removals: 0/1 accepted (fls_def456 rejected - will keep in mapping)
    n/a FLS Additions
    n/a ADD-6 Divergence

Guidelines blocked (2):
  Rule 10.5: Categorization rejected - guideline will not be updated
  Dir 4.12: ADD-6 divergence rejected - reverting to ADD-6 values

Proceed with applying? [y/N]
```

**Escape hatch `--skip-analysis-check --force`:**
- Bypasses all analysis validation
- Prints warning: "WARNING: Skipping analysis check. Decisions will be applied without human review."
- Applies all decisions as-is (no granular filtering)
- Both flags required together as safety measure

---

### Apply Merge Logic (Detailed)

The `apply-verification` tool merges data from **three sources** to compute the final state for each guideline:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Data Sources                                    │
├─────────────────────┬─────────────────────┬─────────────────────────────┤
│ 1. Mapping File     │ 2. Decision Files   │ 3. Analysis + Review State  │
│ (current state)     │ (LLM verification)  │ (human adjustments)         │
│                     │                     │                             │
│ misra_c_to_fls.json │ batch*_decisions/   │ outlier_analysis/           │
│                     │   Rule_10.1.json    │   Rule_10.1.json            │
│                     │   ...               │ review_state.json           │
└─────────────────────┴─────────────────────┴─────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │   Per-Guideline     │
                    │   Merge Logic       │
                    └─────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  Updated Mapping    │
                    │  File               │
                    └─────────────────────┘
```

#### Per-Guideline Processing

For each guideline in the batch:

**Step 1: Load current mapping state**
```python
mapping = load_mapping_file()[guideline_id]
# Contains: applicability, rationale_type, accepted_matches, etc.
```

**Step 2: Load decision file**
```python
decision = load_decision_file(batch, guideline_id)
# Contains: LLM's new values for applicability, rationale_type, accepted_matches, etc.
```

**Step 3: Check if guideline is an outlier**
```python
outlier_file = f"cache/analysis/outlier_analysis/{guideline_id}.json"
is_outlier = os.path.exists(outlier_file)
```

**Step 4: Compute final state**

```python
if not is_outlier:
    # Non-outlier: apply decision as-is
    final_state = decision
else:
    # Outlier: load outlier analysis file and apply with human adjustments
    outlier_analysis = load_json(outlier_file)
    human_review = outlier_analysis.get("human_review", {})
    final_state = merge_with_human_decisions(mapping, decision, human_review)
```

#### Merge Algorithm for Outliers (Per-Context)

The `human_review` object comes from the outlier analysis file and contains **per-context decisions** for FLS changes.

```python
def merge_with_human_decisions(mapping, decision, human_review, guideline_id):
    """
    Merge LLM decision with human review adjustments.
    
    Processes each context (all_rust, safe_rust) separately, respecting
    per-context human decisions for FLS removals and additions.
    
    Args:
        mapping: Current state from misra_c_to_fls.json (v2/v3 structure)
        decision: LLM decision from batch*_decisions/{guideline}.json
        human_review: Human review section from outlier_analysis/{guideline}.json
        guideline_id: For ADD-6 lookup if divergence rejected
    
    Returns:
        Final guideline state with per-context accepted_matches
    """
    final = {
        "guideline_id": guideline_id,
        "schema_version": "3.0",
        "all_rust": {},
        "safe_rust": {},
    }
    
    for ctx in ["all_rust", "safe_rust"]:
        mapping_ctx = mapping.get(ctx, {})
        decision_ctx = decision.get(ctx, {})
        
        # --- Categorization ---
        cat_decision = human_review.get("categorization", {}).get(ctx, {}).get("decision")
        if cat_decision == "accept":
            final[ctx]["applicability"] = decision_ctx.get("applicability")
            final[ctx]["rationale_type"] = decision_ctx.get("rationale_type")
            final[ctx]["adjusted_category"] = decision_ctx.get("adjusted_category")
        else:  # reject or not reviewed
            final[ctx]["applicability"] = mapping_ctx.get("applicability")
            final[ctx]["rationale_type"] = mapping_ctx.get("rationale_type")
            final[ctx]["adjusted_category"] = mapping_ctx.get("adjusted_category")
        
        # --- ADD-6 Divergence Override ---
        add6_ctx_decision = human_review.get("add6_divergence", {}).get(ctx, {}).get("decision")
        if add6_ctx_decision == "reject":
            add6 = load_add6_data().get(guideline_id, {})
            add6_app_key = f"applicability_{ctx}"
            if add6.get(add6_app_key):
                final[ctx]["applicability"] = normalize_add6_applicability(add6[add6_app_key])
            if add6.get("adjusted_category"):
                final[ctx]["adjusted_category"] = add6["adjusted_category"]
        
        # --- FLS Matches (per-context) ---
        final[ctx]["accepted_matches"] = []
        
        mapping_matches = mapping_ctx.get("accepted_matches", [])
        decision_matches = decision_ctx.get("accepted_matches", [])
        
        mapping_fls_ids = {m["fls_id"] for m in mapping_matches if m.get("fls_id")}
        decision_fls_ids = {m["fls_id"] for m in decision_matches if m.get("fls_id")}
        
        retained = mapping_fls_ids & decision_fls_ids
        removed = mapping_fls_ids - decision_fls_ids
        added = decision_fls_ids - mapping_fls_ids
        
        # Include retained matches (use decision's version for updated reasons)
        for match in decision_matches:
            if match.get("fls_id") in retained:
                final[ctx]["accepted_matches"].append(match)
        
        # Handle removals: include if human rejected the removal FOR THIS CONTEXT
        fls_removals = human_review.get("fls_removals", {})
        for match in mapping_matches:
            fls_id = match.get("fls_id")
            if fls_id in removed:
                # Get per-context decision
                removal_ctx_decision = fls_removals.get(fls_id, {}).get(ctx, {}).get("decision")
                if removal_ctx_decision == "reject":
                    # Human rejected removal for this context, keep it
                    final[ctx]["accepted_matches"].append(match)
                # else: removal accepted (or n_a), don't include
        
        # Handle additions: include if human accepted the addition FOR THIS CONTEXT
        fls_additions = human_review.get("fls_additions", {})
        for match in decision_matches:
            fls_id = match.get("fls_id")
            if fls_id in added:
                # Get per-context decision
                addition_ctx_decision = fls_additions.get(fls_id, {}).get(ctx, {}).get("decision")
                if addition_ctx_decision == "accept":
                    # Human accepted addition for this context, include it
                    final[ctx]["accepted_matches"].append(match)
                # else: addition rejected (or n_a), don't include
        
        # --- Specificity restoration ---
        # If human rejected specificity loss, restore lost paragraphs
        specificity_decision = human_review.get("specificity", {}).get("decision")
        if specificity_decision == "reject":
            # Restore any lost paragraph-level matches from mapping
            lost_paragraph_ids = {
                p["fls_id"] for p in 
                human_review.get("specificity", {}).get("lost_paragraphs", [])
            }
            current_ids = {m["fls_id"] for m in final[ctx]["accepted_matches"]}
            for match in mapping_matches:
                fls_id = match.get("fls_id")
                if fls_id in lost_paragraph_ids and fls_id not in current_ids:
                    final[ctx]["accepted_matches"].append(match)
        
        # Copy other fields from decision
        final[ctx]["confidence"] = "high"
        final[ctx]["verified"] = True
        final[ctx]["verified_by_session"] = decision.get("session_id")
        final[ctx]["analysis_summary"] = decision_ctx.get("analysis_summary")
        final[ctx]["rejected_matches"] = decision_ctx.get("rejected_matches", [])
        final[ctx]["notes"] = decision_ctx.get("notes")
    
    return final
```

#### Per-Context Decision Flow

```
For each context (all_rust, safe_rust):
│
├─► Categorization
│   ├─ accept → use decision's applicability/rationale_type/category
│   └─ reject → use mapping's values
│
├─► ADD-6 Divergence (if flagged)
│   ├─ accept → keep decision values
│   └─ reject → override with ADD-6 values
│
├─► FLS Removals (for each removed ID in this context)
│   ├─ accept → ID not in final matches
│   ├─ reject → ID restored from mapping
│   └─ n_a   → ID wasn't in this context
│
├─► FLS Additions (for each added ID in this context)
│   ├─ accept → ID included from decision
│   ├─ reject → ID not included
│   └─ n_a   → ID wasn't added in this context
│
└─► Specificity (global, affects both contexts)
    ├─ accept → lost paragraphs stay removed
    └─ reject → lost paragraphs restored to their original contexts
```

#### Example Walkthrough (Per-Context)

**Guideline: Dir 4.3** (Assembly encapsulation)

**Current mapping (v2.1):**
```json
{
  "all_rust": {
    "applicability": "yes",
    "rationale_type": "direct_mapping",
    "accepted_matches": [
      {"fls_id": "fls_z1il3w9nulzy", "fls_title": "Inline Assembly", "category": 0},
      {"fls_id": "fls_3fg60jblx0xb", "fls_title": "Inline Assembly legality", "category": -2},
      {"fls_id": "fls_4lb6yh12w1cv", "fls_title": "asm macro invocation", "category": -2}
    ]
  },
  "safe_rust": {
    "applicability": "no",
    "rationale_type": "rust_prevents",
    "accepted_matches": [
      {"fls_id": "fls_s5nfhBFOk8Bu", "fls_title": "Unsafety legality", "category": -2}
    ]
  }
}
```

**Decision file (v3.1):**
```json
{
  "all_rust": {
    "applicability": "yes",
    "rationale_type": "direct_mapping",
    "accepted_matches": [
      {"fls_id": "fls_z1il3w9nulzy", "fls_title": "Inline Assembly", "category": 0},
      {"fls_id": "fls_s5nfhBFOk8Bu", "fls_title": "Unsafety legality", "category": -2}
    ]
  },
  "safe_rust": {
    "applicability": "no",
    "rationale_type": "rust_prevents",
    "accepted_matches": [
      {"fls_id": "fls_s5nfhBFOk8Bu", "fls_title": "Unsafety legality", "category": -2}
    ]
  }
}
```

**Changes detected:**
- `all_rust`: Removed `fls_3fg60jblx0xb`, `fls_4lb6yh12w1cv` (paragraph-level!), added `fls_s5nfhBFOk8Bu`
- `safe_rust`: No changes
- Flag: `specificity_decreased` (lost 2 paragraph-level matches)

**Human review (per-context):**
```json
{
  "categorization": {
    "all_rust": { "decision": "accept" },
    "safe_rust": { "decision": "accept" }
  },
  "fls_removals": {
    "fls_3fg60jblx0xb": {
      "all_rust": { "decision": "reject", "reason": "Keep - directly relevant legality rule" },
      "safe_rust": { "decision": "n_a" }
    },
    "fls_4lb6yh12w1cv": {
      "all_rust": { "decision": "reject", "reason": "Keep - asm macro invocation rule" },
      "safe_rust": { "decision": "n_a" }
    }
  },
  "fls_additions": {
    "fls_s5nfhBFOk8Bu": {
      "all_rust": { "decision": "accept", "reason": "Unsafety context is relevant" },
      "safe_rust": { "decision": "n_a" }
    }
  },
  "specificity": {
    "decision": "reject",
    "reason": "Restore lost paragraph-level matches"
  },
  "add6_divergence": {
    "all_rust": { "decision": "n_a" },
    "safe_rust": { "decision": "n_a" }
  }
}
```

**Computed final state:**
```json
{
  "all_rust": {
    "applicability": "yes",
    "rationale_type": "direct_mapping",
    "accepted_matches": [
      {"fls_id": "fls_z1il3w9nulzy", ...},  // retained
      {"fls_id": "fls_3fg60jblx0xb", ...},  // restored (removal rejected)
      {"fls_id": "fls_4lb6yh12w1cv", ...},  // restored (removal rejected)
      {"fls_id": "fls_s5nfhBFOk8Bu", ...}   // added (human accepted)
    ],
    "confidence": "high",
    "verified": true
  },
  "safe_rust": {
    "applicability": "no",
    "rationale_type": "rust_prevents",
    "accepted_matches": [
      {"fls_id": "fls_s5nfhBFOk8Bu", ...}   // retained (no changes)
    ],
    "confidence": "high",
    "verified": true
  }
}
```

**Key outcomes:**
- Categorization accepted for both contexts
- Paragraph-level legality rules restored in `all_rust` (human rejected removals)
- New unsafety match accepted in `all_rust`
- `safe_rust` unchanged (no removal/addition decisions needed)

#### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Non-outlier guideline | Apply decision as-is (no outlier analysis file exists) |
| Outlier with all aspects accepted | Apply decision as-is |
| Outlier with no `human_review` section | **Block apply** - outlier not reviewed |
| Outlier with `overall_status: partial` | **Block apply** - must complete review |
| Missing context decision for FLS ID | **Block apply** - require explicit decision |
| Categorization rejected (one context) | Keep mapping's values for that context only |
| ADD-6 divergence rejected (one context) | Override with ADD-6 values for that context only |
| All FLS additions rejected | Final has only retained + rejected-removal FLS IDs |
| FLS ID only in one context | Other context should have `decision: "n_a"` |
| Specificity rejected | Restore all lost paragraph-level matches to their original contexts |
| Guideline not in decision files | Skip (shouldn't happen, but warn) |
| Outlier file exists but decision file missing | Error (inconsistent state) |

**Strict validation:** Unlike the previous design, we do NOT default missing decisions. All applicable context decisions must be explicit. This ensures human has seen and decided on each aspect.

#### Bulk Rules Application

Before per-guideline processing, bulk rules from `review_state.json` are applied to outlier analysis files:

```python
def apply_bulk_rules(review_state_path, outlier_dir):
    """
    Apply bulk rules to outlier files that don't yet have decisions for those FLS IDs.
    This is called at the start of apply-verification.
    """
    review_state = load_json(review_state_path)
    bulk = review_state.get("bulk_rules", {})
    
    for outlier_file in glob(f"{outlier_dir}/*.json"):
        outlier = load_json(outlier_file)
        human_review = outlier.setdefault("human_review", {})
        modified = False
        
        # Get FLS IDs that were removed/added for this guideline
        comparison = outlier.get("context", {}).get("comparison", {})
        
        # Apply bulk removal acceptances
        fls_removals = human_review.setdefault("fls_removals", {})
        for context in ["all_rust", "safe_rust"]:
            removed_ids = comparison.get(context, {}).get("fls_removed", [])
            for fls_id in removed_ids:
                if fls_id in bulk.get("accept_removals", []):
                    if fls_id not in fls_removals or fls_removals[fls_id].get("decision") is None:
                        fls_removals[fls_id] = {
                            "decision": "accept",
                            "via_bulk_rule": True
                        }
                        modified = True
        
        # Apply bulk addition acceptances
        fls_additions = human_review.setdefault("fls_additions", {})
        for context in ["all_rust", "safe_rust"]:
            added_ids = comparison.get(context, {}).get("fls_added", [])
            for fls_id in added_ids:
                if fls_id in bulk.get("accept_additions", []):
                    if fls_id not in fls_additions or fls_additions[fls_id].get("decision") is None:
                        fls_additions[fls_id] = {
                            "decision": "accept",
                            "via_bulk_rule": True
                        }
                        modified = True
        
        if modified:
            save_json(outlier_file, outlier)
```

---

## Workflow Summary

### Phase 1: Extraction (LLM)
```bash
uv run extract-comparison-data --standard misra-c --batches 1,2,3
```

### Phase 2: Analyze Outliers (LLM, incremental)
```bash
uv run list-pending-outliers
uv run diff-fls-matches --guideline "Rule 10.1"
uv run record-outlier-analysis --guideline "Rule 10.1" ...
```

**Important:** LLM must provide per-FLS-ID justifications in `record-outlier-analysis` to enable granular human review.

### Phase 3: Generate Reports (LLM)
```bash
uv run generate-analysis-reports
```

### Phase 4: Human Review (Hierarchical)

1. **Read final report:** `cache/analysis/reports/final_report.md`
   - Executive summary, highlights per batch, recommendations
   
2. **Drill into batch reports:** `cache/analysis/reports/batch{N}_report.md`
   - Pattern conformance, rationale distribution, outlier verdicts
   
3. **Drill into cross-batch:** `cache/analysis/reports/cross_batch_report.md`
   - Systematic FLS changes, rationale transitions, quality trajectory

4. **Optional: Drill into individual outlier JSONs**
   - Full context including MISRA text, FLS content excerpts
   - `cache/analysis/outlier_analysis/{guideline}.json`

5. **Interactive review with granular decisions:**
   ```bash
   # Set bulk rules for systematic patterns first
   uv run review-outliers --accept-removal fls_xyz123  # Over-matched section
   
   # Then review remaining outliers
   uv run review-outliers
   ```

### Phase 5: Apply (with gate)
```bash
uv run apply-verification \
    --standard misra-c \
    --batch 1,2,3 \
    --analysis-dir cache/analysis/
```

### Phase 6: Cleanup
```bash
rm -rf cache/analysis/
```

---

## Thresholds

| Type | Threshold | Rationale |
|------|-----------|-----------|
| FLS removed | Any (1+) | Any removal needs justification |
| FLS added | Any (1+) | Any addition needs justification |
| Specificity decreased | See below | Paragraph-level matches lost |
| Systematic pattern | >= 2 occurrences | 2+ = potential pattern worth noting |
| Categorization differs | Any | Deviation from ADD-6 needs reasoning |
| Missing analysis_summary | v3.1 only | v3.0 (batch 1) doesn't have it by design |
| Multi-dimension outlier | >= 2 flags | Multiple issues = higher priority |

---

## Specificity Preservation

### The Problem

FLS content has two levels of specificity:

| Category Code | Name | Specificity | Value for Guidelines |
|---------------|------|-------------|---------------------|
| `0` | Section Headers | **Section-level** | Low - just containers |
| `-1` | General/Intro | Paragraph-level | Low |
| `-2` | Legality Rules | **Paragraph-level** | **High** - quotable |
| `-3` | Dynamic Semantics | **Paragraph-level** | **High** - quotable |
| `-4` | Undefined Behavior | **Paragraph-level** | **Highest** - essential |
| `-5` | Implementation Requirements | Paragraph-level | Medium |

**Core principle:** Paragraph-level matches (category < 0) contain quotable normative text. Section-level matches (category = 0) are just headings/containers with no normative content.

**Why this matters:** The goal of FLS mappings is to provide citable text for writing coding guidelines. A mapping like:

- Good: `fls_3fg60jblx0xb` (Legality Rules paragraph): *"Inline assembly is written as an assembly code block wrapped inside a macro invocation."*
- Bad: `fls_z1il3w9nulzy` (Section header): *"Inline Assembly"* - says nothing useful

### Flag Computation

The `specificity_decreased` flag is set when:
1. The mapping had paragraph-level matches (category < 0)
2. Those specific paragraph IDs were removed in the decision
3. The decision has fewer paragraph-level matches than the mapping

```python
def compute_specificity_decreased(mapping_matches: list, decision_matches: list) -> bool:
    """
    Check if the decision lost paragraph-level specificity compared to mapping.
    
    Returns True if:
    - Mapping had paragraph-level matches (category != 0)
    - Those paragraph IDs were removed
    - Decision has fewer paragraph-level matches overall
    """
    def paragraph_ids(matches: list) -> set:
        return {m.get("fls_id") for m in matches 
                if m.get("category", 0) != 0 and m.get("fls_id")}
    
    mapping_paragraphs = paragraph_ids(mapping_matches)
    decision_paragraphs = paragraph_ids(decision_matches)
    
    # Lost paragraphs = mapping paragraphs not in decision
    lost = mapping_paragraphs - decision_paragraphs
    
    # Flag if we lost paragraphs AND ended up with fewer paragraph-level matches
    if lost and len(decision_paragraphs) < len(mapping_paragraphs):
        return True
    
    return False
```

### Analysis Requirements

When `specificity_decreased` flag is set, the analysis must:

1. **Identify each lost paragraph** with its category and title
2. **Explain why removal is appropriate** for each, using one of:
   - **Replaced with better paragraph:** A different, more relevant paragraph-level match was added
   - **False positive:** The original paragraph discusses unrelated concepts
   - **Incorrect category:** The original match was mislabeled
3. **Reject if justification is weak**, such as:
   - "Consolidated into section header"
   - "Section captures the same content"
   - "Simplified for clarity"

### Verdict Guidance

| Justification | Verdict |
|---------------|---------|
| Replaced with different paragraph that's more relevant | `appropriate` |
| Original paragraph was false positive (discusses X, not MISRA concern Y) | `appropriate` |
| Original paragraph had incorrect category in extraction | `appropriate` |
| "Consolidated into section header" | `inappropriate` |
| "Section header captures same content" | `inappropriate` |
| "Simplified" without replacement paragraph | `inappropriate` |
| No justification provided | `needs_review` |

---

## Entry Points

Add to `tools/pyproject.toml`:

```toml
[project.scripts]
# ... existing entries ...

# Comparison analysis tools
extract-comparison-data = "fls_tools.standards.analysis.extract:main"
record-outlier-analysis = "fls_tools.standards.analysis.record:main"
list-pending-outliers = "fls_tools.standards.analysis.pending:main"
diff-fls-matches = "fls_tools.standards.analysis.diff:main"
generate-analysis-reports = "fls_tools.standards.analysis.reports:main"
review-outliers = "fls_tools.standards.analysis.review:main"
reset-review = "fls_tools.standards.analysis.reset_review:main"
```

---

## Module Structure

```
tools/src/fls_tools/standards/analysis/
├── __init__.py
├── shared.py           # Loading, normalization, flag computation, FLS content loading
├── extract.py          # extract-comparison-data
├── record.py           # record-outlier-analysis
├── pending.py          # list-pending-outliers
├── diff.py             # diff-fls-matches
├── reports.py          # generate-analysis-reports
├── review.py           # review-outliers
└── reset_review.py     # reset-review
```

---

## `reset-review` Tool

**Purpose:** Clear human review decisions from outlier analysis files to allow re-review.

**Command:**
```bash
# Reset a single guideline
uv run reset-review --standard misra-c --guideline "Rule 10.1"

# Reset all guidelines in a batch
uv run reset-review --standard misra-c --batch 1

# Reset all guidelines across all batches
uv run reset-review --standard misra-c --all

# Preview what would be reset without making changes
uv run reset-review --standard misra-c --batch 1 --dry-run
```

**Behavior:**
1. Loads the specified outlier analysis file(s)
2. Removes the `human_review` section from each file
3. Preserves all other data (LLM analysis, comparison data, context)
4. Updates `review_state.json` to reflect the reset

**Options:**
- `--guideline`: Reset a single guideline
- `--batch`: Reset all guidelines in a specific batch
- `--all`: Reset all guidelines across all batches
- `--dry-run`: Show what would be reset without saving
- `--force`: Required for `--all` to prevent accidental full reset

**Safety:**
- `--all` requires `--force` to confirm intent
- Always shows count of files affected before proceeding
- `--dry-run` allows preview without modification

---

## Cross-Batch Analysis Questions

The analysis should answer:

1. **Did batch definitions predict verification outcomes?**
2. **Are certain FLS sections being systematically removed/added?**
3. **How does rationale_type distribute across batches?**
4. **Where do decisions diverge from ADD-6, and is there a pattern?**
5. **Is there quality difference between v3.0 and v3.1 decisions?**
6. **Are outliers evenly distributed or concentrated?**

---

## Execution: Processing 145 Outliers

### Pre-Execution Checklist

Before starting outlier processing:

1. ✅ Comparison data extracted (`cache/analysis/comparison_data/batch{1,2,3}/`)
2. ✅ `cache/analysis/outlier_analysis/` directory exists
3. ✅ `record-outlier-analysis` tool updated to per-aspect interface
4. ✅ Plan reviewed and approved

### Processing Protocol

For each guideline, the LLM:

1. **Reads comparison data** from `cache/analysis/comparison_data/batch{N}/{guideline}.json`
2. **Analyzes each flagged aspect:**
   - Categorization changes (applicability, adjusted_category, rationale_type)
   - FLS removals (each removed ID with justification)
   - FLS additions (when 2+ added, each added ID with justification)
   - ADD-6 divergence (if flags indicate divergence)
3. **Records verdict** using `record-outlier-analysis` with per-aspect arguments
4. **Proceeds to next guideline**

Processing is done silently in batches. At the end, output:
- Total processed count
- Per-recommendation distribution (accept/accept_with_notes/needs_review/reject)
- Any guidelines that failed to record

### Compaction Recovery

**If context compaction occurs mid-processing:**

1. Note the last successfully recorded guideline before compaction
2. On session resume, run: `ls cache/analysis/outlier_analysis/ | wc -l` to count completed
3. Run: `uv run list-pending-outliers --standard misra-c --batches 1,2,3` to see remaining
4. Resume from the first pending guideline

**The LLM should note in the Processing Log section if compaction occurred.**

### Processing Order

1. Batch 1 (20 guidelines) - High-score direct mappings
2. Batch 2 (118 guidelines) - Not applicable  
3. Batch 3 (7 guidelines) - Stdlib & Resources

### Output Expectations

After all 145 are processed:
- 145 files in `cache/analysis/outlier_analysis/`
- Each file contains full context + LLM analysis with per-aspect verdicts
- Ready for report generation (Phase 3)

---

## Processing Log

**Started:** 2026-01-08T02:00:00Z
**Batch 1:** ✅ Complete (20 guidelines)
**Batch 2:** ✅ Complete (118 guidelines)  
**Batch 3:** ✅ Complete (7 guidelines)
**Completed:** 2026-01-08T03:00:00Z

### Summary

- **Total processed:** 145/145 guidelines
- **All 145 files created in `cache/analysis/outlier_analysis/`**
- **Reports generated in `cache/analysis/reports/`**

### Results by Batch

**Batch 1 (20 guidelines - High-score direct mappings):**
- 19 accept
- 1 needs_review (Rule 5.9 - ADD-6 divergence questionable)

**Batch 2 (118 guidelines - Not applicable):**
- 117 had null decisions (never verified) → all marked needs_review
- 1 verified (Dir 4.6) → accept

**Batch 3 (7 guidelines - Stdlib & Resources):**
- All 7 had null decisions (never verified) → all marked needs_review

### Key Finding (INCORRECT - BUG DISCOVERED)

**The above analysis was WRONG.** Batches 2 and 3 WERE verified with full decision content.

**Root Cause:** A schema version mismatch bug in `is_v2_family()`:
- Decision files use `schema_version: "3.1"` 
- `is_v2_family()` only recognizes `"2.0", "2.1", "3.0"`
- Since "3.1" wasn't in the list, `is_v2_family()` returned `False`
- The extraction code treated decision files as v1 flat structure
- This caused it to look for `.decision` key instead of `.all_rust`/`.safe_rust`
- All decision data appeared as `null`

**Impact:**
- 124 outlier analyses incorrectly stated "NOT VERIFIED - decision null"
- These analyses are invalid and must be re-run after the fix

---

## Bug Fix Required

### Fix 1: Update `is_v2_family()` to recognize v3.1+

**File:** `tools/src/fls_tools/shared/schema_version.py`

**Change:** Line 66-68, update to recognize v3.x versions:

```python
def is_v2_family(data: Dict[str, Any]) -> bool:
    """Check if data is v2 family (v2.0, v2.1, or v3.x - per-context structure)."""
    version = detect_schema_version(data)
    # v2.0, v2.1, and any v3.x use per-context structure
    return version in ("2.0", "2.1") or version.startswith("3.")
```

### Fix 2: Re-extract comparison data

After fixing the schema version function, re-run extraction:

```bash
cd tools
rm -rf ../cache/analysis/comparison_data/
rm -rf ../cache/analysis/outlier_analysis/
uv run extract-comparison-data --standard misra-c --batches 1,2,3
```

### Fix 3: Re-run outlier analysis

Process all 145 guidelines again with correct comparison data.

---

## Next Steps

1. ~~Implement tools in `tools/src/fls_tools/standards/analysis/`~~ ✅
2. ~~Add entry points to `pyproject.toml`~~ ✅
3. ~~Extend `apply-verification` with analysis gate~~ ✅ (partial)
4. ~~Run extraction and generate comparison data~~ ✅ (re-run after fix)
5. ~~**FIX:** Update `is_v2_family()` to recognize v3.1~~ ✅
6. ~~**RE-RUN:** Extract comparison data with fixed code~~ ✅
7. **IN PROGRESS:** LLM analyzes outliers (145 guidelines) 
8. Generate reports
9. Human reviews via interactive tool
10. Apply verified decisions

### Fix Applied (2026-01-08)

**File:** `tools/src/fls_tools/shared/schema_version.py`

```python
# Before (line 66-68):
def is_v2_family(data: Dict[str, Any]) -> bool:
    """Check if data is v2 family (v2.0, v2.1, or v3.0 - per-context structure)."""
    return detect_schema_version(data) in ("2.0", "2.1", "3.0")

# After:
def is_v2_family(data: Dict[str, Any]) -> bool:
    """Check if data is v2 family (v2.0, v2.1, or v3.x - per-context structure)."""
    version = detect_schema_version(data)
    return version in ("2.0", "2.1") or str(version).startswith("3.")
```

Also updated `is_v3()` to recognize v3.x and updated module docstring.

**Re-extraction results (with fix):**
- Batch 1: 20 guidelines, 20 flagged as outliers
- Batch 2: 118 guidelines, 117 flagged as outliers  
- Batch 3: 7 guidelines, 7 flagged as outliers
- Total: 145 guidelines, 144 outliers

Now correctly shows decision content (not null) in comparison data.

---

## Validation Enhancement (2026-01-08)

### Problem

The `record-outlier-analysis` tool was accepting incomplete analysis:
1. Missing per-FLS-ID details (`--fls-removal-detail` and `--fls-addition-detail`)
2. Missing overall verdicts only generated warnings, not errors

This would produce analysis files that lack the granular per-ID justifications needed for:
- Meaningful report generation
- Granular human review (accept/reject individual FLS changes)

### Solution

Enhanced `record-outlier-analysis` with strict validation:

1. **Per-ID coverage validation:** Tool now validates that every removed/added FLS ID has a corresponding `--fls-removal-detail` or `--fls-addition-detail` argument

2. **Verdict validation as errors:** Missing verdicts (categorization, fls-removals, fls-additions, add6-divergence, specificity) are now errors, not warnings

3. **No bypass mechanism:** Validation cannot be bypassed. If validation fails, fix the input.

### Validation Behavior

| Condition | Behavior |
|-----------|----------|
| Missing overall verdict | ERROR, exit 1 |
| Missing per-ID removal detail | ERROR, exit 1 |
| Missing per-ID addition detail | ERROR, exit 1 |

### Example Error Output

```
ERROR: Rule 11.4 has validation errors:
  - Missing --fls-removal-detail for: fls_1qhsun1vyarz, fls_ppd1xwve3tr7
  - Missing --fls-addition-detail for: fls_8i4jzksxlrw0, fls_9wgldua1u8yt
```

### Impact

- All 145 outlier analyses will have complete per-ID justifications
- Reports will show detailed reasoning for each FLS change
- Human reviewers can make granular per-context accept/reject decisions

---

## Incomplete Analysis Files (2026-01-08)

### Problem

9 analysis files were created **before** per-ID validation was added to the tool. These files have missing `removal_decisions` and/or `addition_decisions` for some FLS IDs.

### Affected Files

| File | Missing Removal Details | Missing Addition Details |
|------|------------------------|-------------------------|
| Dir_4.3 | 0 | 1 |
| Dir_5.1 | 4 | 2 |
| Rule_10.5 | 4 | 4 |
| Rule_11.1 | 3 | 3 |
| Rule_5.1 | 4 | 4 |
| Rule_5.9 | 4 | 5 |
| Rule_8.6 | 4 | 3 |
| Rule_9.4 | 6 | 5 |
| Rule_9.7 | 5 | 5 |
| **Total** | **34** | **32** |

### Root Cause

These files were created between 05:23-05:49 on 2026-01-08. The per-ID validation was added at 05:59. Files created after 05:59 are complete.

### Resolution

These 9 files must be re-recorded with `--force` and proper `--fls-removal-detail` / `--fls-addition-detail` arguments for each missing FLS ID.

---

## Enforced Single-Guideline Analysis (2026-01-09)

### Problem Identified

LLM batch-processing of guidelines led to:
1. **Pattern matching** instead of genuine analysis - recognizing "standard patterns" without examining specifics
2. **Shallow reasoning** that restates comparison data without evaluating actual FLS content
3. **Missing nuances** - not reading the actual text of removed/added FLS sections

The core issue: when reading multiple comparison files at once, the LLM optimizes for speed over depth, generating plausible-sounding analysis without actually:
- Reading the **content** of removed FLS sections to assess if they were valuable
- Checking if added FLS sections actually address the MISRA concern better
- Evaluating whether ADD-6 divergence is genuinely justified

### Solution: Enforced Single-Guideline Workflow

#### New Tool: `prepare-outlier-analysis`

A tool that displays everything needed to analyze ONE guideline, including full FLS content for removed/added sections.

**Purpose:**
- Force the LLM to see actual FLS text before making judgments
- Provide all context in a single output that must be read
- Generate a template command showing required flags
- Enable general recommendations based on FLS content review

**Usage:**
```bash
uv run prepare-outlier-analysis --standard misra-c --guideline "Rule 9.7" --batch 1
```

**Output Structure:**
```
================================================================================
OUTLIER ANALYSIS: Rule 9.7 (Batch 1)
================================================================================

MISRA CONCERN: [Title from standards file]
ADD-6: all_rust=Yes, safe_rust=No, adjusted_category=required, rationale=[UB]

ACTIVE FLAGS:
  ✓ adjusted_category_differs_from_add6 (safe_rust)
  ✓ fls_removed (2 IDs)
  ✓ fls_added (3 IDs)

--------------------------------------------------------------------------------
CONTEXT: all_rust
--------------------------------------------------------------------------------
Decision: applicability=yes, rationale_type=direct_mapping, adjusted_category=required
Mapping:  applicability=yes, rationale_type=direct_mapping, adjusted_category=required
ADD-6:    applicability=Yes, adjusted_category=required

Changes from mapping: None
Divergence from ADD-6: None

FLS REMOVED (from mapping → not in decision):

  [1] fls_3pjla9s93mhd - "Atomics legality" (category: -2, score: 0.71)
      Mapping reason: "Per FLS: Defines atomic types in core::sync::atomic..."
      
      FLS CONTENT:
      ┌────────────────────────────────────────────────────────────────────────
      │ Module core::sync::atomic defines the following atomic types:
      │ - AtomicBool
      │ - AtomicI8, AtomicI16, AtomicI32, AtomicI64, AtomicIsize
      │ - AtomicU8, AtomicU16, AtomicU32, AtomicU64, AtomicUsize
      │ - AtomicPtr<T>
      │ 
      │ An atomic type provides atomic load, store, and compare-and-swap
      │ operations with configurable memory ordering.
      └────────────────────────────────────────────────────────────────────────
      
      LEGALITY RULES (-2):
        • "An atomic operation shall specify a memory ordering."
        • "Atomic types implement Send and Sync."
      
      DYNAMIC SEMANTICS (-3):
        • "An atomic load returns the current value..."
      
      UNDEFINED BEHAVIOR (-4):
        • (none for this section)

FLS ADDED (in decision → not in mapping):

  [1] fls_46910buiwvv9 - "Initialization legality rule" (category: -2, score: 0.73)
      Decision reason: "FLS states 'A variable shall be initialized before accessed.'"
      
      FLS CONTENT:
      ┌────────────────────────────────────────────────────────────────────────
      │ A variable shall be initialized before it is accessed.
      │ 
      │ The value of a binding is the value of the expression of the
      │ corresponding let initializer.
      └────────────────────────────────────────────────────────────────────────

--------------------------------------------------------------------------------
CONTEXT: safe_rust  
--------------------------------------------------------------------------------
[Similar structure...]

================================================================================
REQUIRED FLAGS (based on active flags):
================================================================================

The following flags MUST be provided:

  --cat-ack-diverge-category-safe-rust "..."   # safe_rust.adjusted_category_differs_from_add6

  --fls-removal-detail "fls_3pjla9s93mhd:all_rust:..."
  --fls-removal-detail "fls_xdvdl2ssnhlo:all_rust:..."
  
  --fls-addition-detail "fls_46910buiwvv9:all_rust:..."
  ...

================================================================================
TEMPLATE COMMAND:
================================================================================

uv run record-outlier-analysis --standard misra-c --guideline "Rule 9.7" --batch 1 \
    --analysis-summary "FILL: 1-2 sentence summary" \
    --overall-recommendation FILL \
    --categorization-verdict-all-rust FILL \
    --categorization-reasoning-all-rust "FILL" \
    --categorization-verdict-safe-rust FILL \
    --categorization-reasoning-safe-rust "FILL" \
    --cat-ack-diverge-category-safe-rust "FILL: Why does safe_rust adjusted_category differ from ADD-6?" \
    --fls-removals-verdict FILL \
    --fls-removals-reasoning "FILL" \
    --fls-removal-detail "fls_3pjla9s93mhd:all_rust:FILL" \
    --fls-removal-detail "fls_xdvdl2ssnhlo:all_rust:FILL" \
    --fls-additions-verdict FILL \
    --fls-additions-reasoning "FILL" \
    --fls-addition-detail "fls_46910buiwvv9:all_rust:FILL" \
    --add6-divergence-verdict FILL \
    --add6-divergence-reasoning "FILL" \
    --general-recommendation "FILL or omit if none" \
    --force
```

#### Enhanced Validation for `record-outlier-analysis`

**Increased minimum justification length:**
- Per-ID justifications: minimum 50 characters (up from no minimum)
- Must contain either an FLS ID reference OR a quoted phrase from FLS content

**Quote/Reference requirement:**
```python
def validate_fls_justification(text: str, fls_id: str) -> list[str]:
    errors = []
    if len(text) < 50:
        errors.append(f"Justification for {fls_id} too short (min 50 chars, got {len(text)})")
    
    # Must reference an FLS ID or contain a quoted phrase
    has_fls_ref = "fls_" in text.lower()
    has_quote = '"' in text or "'" in text or "FLS states" in text or "Per FLS" in text
    if not (has_fls_ref or has_quote):
        errors.append(f"Justification for {fls_id} must quote FLS content or reference an FLS ID")
    
    return errors
```

**Specificity loss enforcement:**
- When `specificity_decreased` flag is set, `--specificity-verdict` cannot be "n_a"
- `--specificity-reasoning` must reference specific lost paragraph IDs

#### New Flag: `--general-recommendation`

For observations that go beyond the single guideline:
- FLS paragraphs that seem relevant but weren't in similarity results
- Patterns noticed across guidelines (e.g., "this FLS section appears relevant to all FFI rules")
- Suggestions for cross-guideline consistency

These are recorded in the analysis file and aggregated in batch reports.

#### Progress Tracking Tool: `check-analysis-progress`

```bash
uv run check-analysis-progress --standard misra-c
```

**Output:**
```
ANALYSIS PROGRESS: misra-c
==========================

Batch 1: 6/20 complete (30%)
  Last completed: Rule 9.4
  Next pending: Rule 9.7

Recent verdicts:
  Dir 4.3:  accept
  Dir 5.1:  accept  
  Rule 5.1: accept
  Rule 5.9: needs_review (ADD-6 divergence questionable)
  Rule 8.6: accept
  Rule 9.4: accept

General recommendations recorded: 2
  - "fls_xyz should be considered for all atomics rules"
  - "Batch 2 FFI guidelines share common divergence pattern"

To continue:
  uv run prepare-outlier-analysis --standard misra-c --guideline "Rule 9.7" --batch 1
```

### LLM Analysis Protocol (for AGENTS.md)

When analyzing outliers, follow this single-guideline workflow:

1. **Prepare**: Run `uv run prepare-outlier-analysis --standard misra-c --guideline "Rule X.Y" --batch N`

2. **Read**: Read the ENTIRE output. Do not skim. The FLS content sections contain the actual specification text needed to evaluate removals/additions.

3. **Analyze Each Removal**: For each FLS ID in "FLS REMOVED":
   - Read the FLS content shown (main content + all rubrics)
   - Decide: Does removing this section lose important information for understanding how Rust handles this MISRA concern?
   - If YES (inappropriate removal): Note why the content is valuable, quote specific text
   - If NO (appropriate removal): Note why the content is redundant or tangential

4. **Analyze Each Addition**: For each FLS ID in "FLS ADDED":
   - Read the FLS content shown
   - Decide: Does this section provide useful information about the MISRA concern?
   - If YES (appropriate addition): Note what value it adds, quote specific text
   - If NO (inappropriate addition): Note why it's not relevant

5. **Evaluate Divergence**: If ADD-6 divergence is flagged:
   - Read the ADD-6 values shown
   - Read the decision values shown
   - Decide: Is the divergence justified by Rust language semantics?

6. **Check for General Recommendations**: While reviewing FLS content, note if:
   - Any FLS paragraphs in rubrics seem relevant but weren't matched
   - This guideline's pattern might apply to other guidelines
   - There's a cross-guideline consistency issue

7. **Fill Template**: Copy the template command and fill in each FILL placeholder:
   - Each justification must be at least 50 characters
   - Each justification must quote or reference specific FLS content
   - Explain the reasoning, not just state the verdict

8. **Record**: Execute the filled command

9. **Checkpoint**: After every 5 guidelines, output a summary showing:
   - Guidelines processed in this batch of 5
   - Verdicts given (accept/needs_review/reject counts)
   - Any general recommendations recorded
   - Any patterns noticed
   - Which guidelines (if any) were marked needs_review and why

### Implementation Plan

#### Phase 1: Create `prepare-outlier-analysis` tool

Location: `tools/src/fls_tools/standards/analysis/prepare.py`

Features:
- Loads comparison data for single guideline
- Loads FLS content for all added/removed IDs (including all rubrics)
- Formats output with actual FLS text in readable blocks
- Shows which flags require acknowledgment
- Generates template command with all required flags pre-filled

Entry point: `prepare-outlier-analysis = "fls_tools.standards.analysis.prepare:main"`

#### Phase 2: Update `record-outlier-analysis` validation

Changes to `tools/src/fls_tools/standards/analysis/record.py`:
- Add `--general-recommendation` flag (optional, aggregated to batch report)
- Increase minimum justification length to 50 chars
- Add quote/reference validation
- Enforce specificity_decreased handling (cannot be n_a when flagged)

#### Phase 3: Create `check-analysis-progress` tool

Location: `tools/src/fls_tools/standards/analysis/progress.py`

Features:
- Shows completion status per batch
- Lists recent verdicts
- Shows pending next guideline
- Aggregates general recommendations

Entry point: `check-analysis-progress = "fls_tools.standards.analysis.progress:main"`

#### Phase 4: Update AGENTS.md

Add "Outlier Analysis Protocol" section with the workflow defined above.

#### Phase 5: Clear existing analysis and restart

```bash
# Backup existing (incomplete) analysis
mv cache/analysis/outlier_analysis cache/analysis/outlier_analysis_backup_20260109

# Create fresh directory
mkdir -p cache/analysis/outlier_analysis

# Re-extract comparison data (if needed)
uv run extract-comparison-data --standard misra-c --batches 1,2,3 --force
```

### Checkpoint Format

After every 5 guidelines, the LLM outputs:

```
================================================================================
CHECKPOINT: Guidelines 6-10 of Batch 1
================================================================================

Completed:
  1. Rule 9.7:  accept - Atomic initialization maps directly to Rust atomics
  2. Rule 10.5: accept - Type casting rules align with FLS cast expressions
  3. Rule 11.1: needs_review - Pointer conversion divergence from ADD-6 questionable
  4. Rule 11.4: accept - Pointer-to-integer cast maps to raw pointer operations
  5. Rule 11.6: accept - Object pointer conversion aligns with FLS unsafety

Summary:
  - Accepted: 4
  - Needs review: 1 (Rule 11.1)
  - Rejected: 0

General recommendations recorded:
  - Rule 11.1: "All pointer rules may need consistent ADD-6 divergence rationale"

Patterns noticed:
  - Rules 11.x share common FLS sections for pointer/unsafety operations
  - safe_rust consistently n_a for pointer manipulation rules

Next: Rule 12.1
================================================================================
```

### Implementation Plan (Detailed)

Based on code review, here's the refined implementation:

#### Phase 1: Fix `load_fls_content` to Handle Paragraph IDs

**Problem:** The current `load_fls_content()` in `analysis/shared.py` only finds section-level FLS IDs. Paragraph-level IDs (like `fls_3fg60jblx0xb`) are stored inside rubrics and aren't found.

**Solution:** Update `load_fls_content()` to use existing `build_fls_metadata()` from `fls_tools.shared.fls` which already builds both `sections_metadata` and `paragraphs_metadata`.

**Changes to `tools/src/fls_tools/standards/analysis/shared.py`:**
```python
from fls_tools.shared import load_fls_chapters, build_fls_metadata

# Module-level cache
_fls_metadata_cache = None

def get_fls_metadata(root: Path | None = None) -> tuple[dict, dict]:
    """Get cached FLS metadata (sections and paragraphs)."""
    global _fls_metadata_cache
    if _fls_metadata_cache is None:
        chapters = load_fls_chapters(root)
        _fls_metadata_cache = build_fls_metadata(chapters)
    return _fls_metadata_cache

def load_fls_content(fls_id: str, root: Path | None = None) -> dict | None:
    """
    Load FLS content by ID (section or paragraph).
    
    For section IDs: Returns section content with all rubrics
    For paragraph IDs: Returns parent section content with paragraph highlighted
    """
    sections_meta, paragraphs_meta = get_fls_metadata(root)
    
    # Check if it's a section ID
    if fls_id in sections_meta:
        return _load_section_content(fls_id, root)
    
    # Check if it's a paragraph ID
    if fls_id in paragraphs_meta:
        para_info = paragraphs_meta[fls_id]
        parent_section = para_info.get("section_fls_id")
        return {
            "fls_id": fls_id,
            "is_paragraph": True,
            "paragraph_text": para_info.get("text", ""),
            "category": para_info.get("category"),
            "category_name": para_info.get("category_name"),
            "parent_section_fls_id": parent_section,
            "parent_section_title": para_info.get("section_title", ""),
            "chapter": para_info.get("chapter"),
            # Also load parent section for context
            "parent_section": _load_section_content(parent_section, root) if parent_section else None,
        }
    
    return None
```

#### Phase 2: Update `prepare-outlier-analysis` Tool

Already created at `tools/src/fls_tools/standards/analysis/prepare.py`. After Phase 1 fix, it will correctly show FLS content for both section and paragraph IDs.

**Entry point added to pyproject.toml:**
```toml
prepare-outlier-analysis = "fls_tools.standards.analysis.prepare:main"
```

#### Phase 3: Update `record-outlier-analysis` Validation

**Changes to `tools/src/fls_tools/standards/analysis/record.py`:**

1. Add `--general-recommendation` flag (optional, stored in analysis file)
2. Increase minimum per-ID justification length to 50 chars
3. Add quote/reference validation:
   - Must contain `fls_` reference OR
   - Must contain quoted text indicators (`"`, `'`, `"FLS states"`, `"Per FLS"`)
4. Specificity enforcement when `specificity_decreased` flag set

#### Phase 4: Create `check-analysis-progress` Tool

**Location:** `tools/src/fls_tools/standards/analysis/analysis_progress.py`

**Features:**
- Shows completion status per batch by counting files in `cache/analysis/outlier_analysis/`
- Lists recent verdicts from completed analysis files
- Shows next pending guideline
- Aggregates general recommendations across all files

**Entry point:** `check-analysis-progress = "fls_tools.standards.analysis.analysis_progress:main"`

#### Phase 5: Update AGENTS.md

Add "Outlier Analysis Protocol" section documenting the single-guideline workflow with checkpoints every 5 guidelines.

#### Phase 6: Clear and Restart Analysis

```bash
# Backup existing analysis
mv cache/analysis/outlier_analysis cache/analysis/outlier_analysis_backup_20260109_v2

# Create fresh directory
mkdir -p cache/analysis/outlier_analysis

# Verify comparison data exists
ls cache/analysis/comparison_data/batch{1,2,3}/ | wc -l
```

### Existing Tools to Reuse

| Tool/Function | Location | Purpose |
|---------------|----------|---------|
| `load_fls_chapters()` | `fls_tools.shared.fls` | Load all chapter JSON files |
| `build_fls_metadata()` | `fls_tools.shared.fls` | Build sections + paragraphs metadata |
| `CATEGORY_NAMES` | `fls_tools.shared.constants` | Rubric category names |
| `load_comparison_data()` | `analysis/shared.py` | Load comparison data for a guideline |
| `get_active_flags()` | `analysis/shared.py` | Get list of active flag names |

### Tool Execution Order

1. `prepare-outlier-analysis` - Displays context for ONE guideline
2. LLM reads output and formulates analysis
3. `record-outlier-analysis` - Records the analysis with validation
4. `check-analysis-progress` - Shows progress and next guideline (every 5)
5. Repeat until batch complete
