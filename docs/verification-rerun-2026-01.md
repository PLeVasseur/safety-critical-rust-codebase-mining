# MISRA C Verification Rerun - January 2026

## Purpose

Re-verify all MISRA C guidelines using updated classification guidance from AGENTS.md.

Key improvements in this run:
- Clear distinction between `no_equivalent` and `rust_alternative`
- Stable semantics for `accepted_matches` and `rejected_matches`
- Four output categories linked to coding guideline actions

## Current State

**Active Batch:** 1 - High-Score Direct Mappings
**Next Action:** Batch 1 - Verify guidelines (0/20 complete)

## How to Continue

Copy this prompt to resume work:

> Continue MISRA C verification rerun. Read `docs/verification-rerun-2026-01.md` for current state and next action.

---

## Quick Reference

- Backup location: `cache/verification-backup-2026-01/misra-c/`
- Verification workflow: See AGENTS.md "MISRA to FLS Verification Workflow"
- Rationale type guidance: See AGENTS.md "FLS Rationale Types"
- Match semantics: See AGENTS.md "Match Semantics"

---

## Progress

| Batch | Guidelines | Status | Session | Comparison |
|-------|------------|--------|---------|------------|
| 1 | 20 | **in progress** | 1 | - |
| 2 | 88 | pending | - | - |
| 3 | 38 | pending | - | - |
| 4 | 55 | pending | - | - |
| 5 | 22 | pending | - | - |

---

## Phase 0: Setup

### Checklist
- [x] Backup existing verification artifacts (105 files → `cache/verification-backup-2026-01/misra-c/`)
- [x] Reset verification state
- [x] Verify clean state with `check-progress` (0 verified, 223 pending)

### Backup Commands
```bash
mkdir -p cache/verification-backup-2026-01/misra-c
cp -r cache/verification/misra-c/* cache/verification-backup-2026-01/misra-c/
cp coding-standards-fls-mapping/verification/misra-c/progress.json cache/verification-backup-2026-01/misra-c/
cp coding-standards-fls-mapping/mappings/misra_c_to_fls.json cache/verification-backup-2026-01/misra-c/
```

### Reset Commands
```bash
cd tools
uv run reset-verification --standard misra-c
uv run check-progress --standard misra-c
```

### Backup Contents
| Source | Files | Description |
|--------|-------|-------------|
| `batch1_decisions/` | 2 | Partial (Rule_15.4, Rule_15.7 - misplaced) |
| `batch2_decisions/` | 88 | Complete |
| `batch4_decisions/` | 9 | Partial |
| `batch5_decisions/` | 4 | Partial |
| `progress.json` | 1 | Progress state (20 verified in Batch 1) |
| `misra_c_to_fls.json` | 1 | Current mapping (20 high-confidence entries) |

---

## Batch 1: High-Score Direct Mappings (20 guidelines)

### Description
Re-review existing high-confidence entries + direct mappings with similarity >= 0.65

### Comparison Points
Compare new decisions with current mapping file entries (20 high-confidence).

### Status
- [x] Batch report generated (`cache/verification/misra-c/batch1_session1.json`)
- [ ] All 20 guidelines verified
- [ ] Comparison analysis complete
- [ ] Merged and applied

### Comparison Results

#### Summary
| Metric | Value |
|--------|-------|
| Total guidelines | 20 |
| Rationale type changes | - |
| Accepted matches changes | - |
| New rejections added | - |

#### Significant Changes
[To be filled after comparison]

#### Lessons Learned
[To be filled after comparison]

---

## Batch 2: Not Applicable (88 guidelines)

### Description
Guidelines marked `applicability_all_rust: not_applicable` - still require FLS justification.

### Comparison Points
Compare new decisions with:
1. Current mapping file
2. Backup decision files at `cache/verification-backup-2026-01/misra-c/batch2_decisions/`

### Special Attention
9 guidelines identified for potential rationale type changes:

| Guideline | Expected Rationale | Reason |
|-----------|-------------------|--------|
| Dir 4.6 | `rust_alternative` | Explicit integer types are Rust's alternative |
| Dir 4.8 | `rust_alternative` | Visibility system is Rust's alternative |
| Dir 4.10 | `no_equivalent` | No headers in Rust (keep as-is) |
| Rule 1.4 | `no_equivalent` | Meta-info; move accepted to rejected |
| Rule 2.4 | `rust_alternative` | Compiler lints are Rust's alternative |
| Rule 3.2 | `no_equivalent` | No line splicing (keep as-is) |
| Rule 4.1 | `no_equivalent` | Unambiguous escapes (keep as-is) |
| Rule 5.4 | `rust_alternative` | Macro hygiene is Rust's alternative |
| Rule 5.7 | `rust_alternative` | Namespace design is Rust's alternative |

### Status
- [ ] Batch report generated
- [ ] All 88 guidelines verified
- [ ] Comparison analysis complete
- [ ] Merged and applied

### Comparison Results

#### Summary
| Metric | Value |
|--------|-------|
| Total guidelines | 88 |
| Rationale type changes | - |
| Accepted matches changes | - |
| New rejections added | - |

#### Significant Changes
[To be filled after comparison]

#### Lessons Learned
[To be filled after comparison]

---

## Batch 3: Stdlib & Resources (38 guidelines)

### Description
Categories 21+22 remaining `direct` guidelines (standard library and resources).

### Comparison Points
Compare new decisions with current mapping file.

### Status
- [ ] Batch report generated
- [ ] All 38 guidelines verified
- [ ] Comparison analysis complete
- [ ] Merged and applied

### Comparison Results

#### Summary
| Metric | Value |
|--------|-------|
| Total guidelines | 38 |
| Rationale type changes | - |
| Accepted matches changes | - |
| New rejections added | - |

#### Significant Changes
[To be filled after comparison]

#### Lessons Learned
[To be filled after comparison]

---

## Batch 4: Medium-Score Direct (55 guidelines)

### Description
Remaining `direct` with similarity score 0.5-0.65.

### Comparison Points
Compare new decisions with:
1. Current mapping file
2. Backup decision files (9 partial): Rule_15.5, Rule_5.8, Rule_7.1, Rule_7.2, Rule_8.15, Rule_8.3, Rule_8.5, Rule_8.7, Rule_8.9

### Status
- [ ] Batch report generated
- [ ] All 55 guidelines verified
- [ ] Comparison analysis complete
- [ ] Merged and applied

### Comparison Results

#### Summary
| Metric | Value |
|--------|-------|
| Total guidelines | 55 |
| Rationale type changes | - |
| Accepted matches changes | - |
| New rejections added | - |

#### Significant Changes
[To be filled after comparison]

#### Lessons Learned
[To be filled after comparison]

---

## Batch 5: Edge Cases (22 guidelines)

### Description
`partial`, `rust_prevents`, and any remaining guidelines.

### Comparison Points
Compare new decisions with:
1. Current mapping file
2. Backup decision files (4 partial): Rule_15.6, Rule_16.3, Rule_8.12, Rule_8.16

### Status
- [ ] Batch report generated
- [ ] All 22 guidelines verified
- [ ] Comparison analysis complete
- [ ] Merged and applied

### Comparison Results

#### Summary
| Metric | Value |
|--------|-------|
| Total guidelines | 22 |
| Rationale type changes | - |
| Accepted matches changes | - |
| New rejections added | - |

#### Significant Changes
[To be filled after comparison]

#### Lessons Learned
[To be filled after comparison]

---

## Final Analysis

### Overall Statistics
| Metric | Value |
|--------|-------|
| Total guidelines verified | - |
| Total rationale type changes | - |
| `no_equivalent` count | - |
| `rust_alternative` count | - |
| `rust_prevents` count | - |
| `direct_mapping` count | - |
| `partial_mapping` count | - |

### Key Findings
[To be filled after all batches complete]

### Recommendations
[To be filled after all batches complete]
