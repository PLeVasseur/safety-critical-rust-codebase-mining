# Schema Migration: v1 → v2 (Per-Context Applicability)

## Overview

Migrate from flat applicability fields to nested per-context structures with independent verification for `all_rust` and `safe_rust`.

**Created:** 2026-01-02
**Status:** Phase 6 - Execute fresh verification

---

## Current State

| Phase | Status | Completed |
|-------|--------|-----------|
| 0. Create tracking document | complete | 2026-01-02 |
| 1. Tag existing data with v1 | complete | 2026-01-02 |
| 2. Update schema definitions | complete | 2026-01-02 |
| 3. Update tools | complete | 2026-01-02 |
| 4. Update verification workflow | complete | 2026-01-02 |
| 5. Update AGENTS.md | complete | 2026-01-02 |
| 6. Execute fresh verification | **in_progress** | - |
| 7. Cleanup (post-migration) | pending | - |

**Next Action:** Phase 6 - Verify Batch 3 (Stdlib & Resources).

---

## Quick Reference

- Backup location: `cache/verification-backup-2026-01/misra-c/`
- Main mapping file: `coding-standards-fls-mapping/mappings/misra_c_to_fls.json`
- Schema files: `coding-standards-fls-mapping/schema/`
- Tools: `tools/src/fls_tools/`

---

## Schema Version Placement

| File Type | Location of `schema_version` |
|-----------|------------------------------|
| Mapping file (`misra_c_to_fls.json`) | Per-guideline entry (allows mixed v1/v2) |
| Progress file (`progress.json`) | Top-level |
| Decision files (`*.json` in batch directories) | Top-level |
| Batch reports (`batch*_session*.json`) | Top-level |

---

## Phase 0: Create Tracking Document

### Checklist
- [x] Create this file (`docs/schema-migration-v1-to-v2.md`)
- [x] Review and confirm plan with user

---

## Phase 1: Tag Existing Data with v1

Add `"schema_version": "1.0"` to all existing files.

### Files to Update

| File | Entries | Status |
|------|---------|--------|
| `coding-standards-fls-mapping/mappings/misra_c_to_fls.json` | 223 guideline entries | complete |
| `cache/verification-backup-2026-01/misra-c/misra_c_to_fls.json` | 223 guideline entries | complete |
| `cache/verification-backup-2026-01/misra-c/progress.json` | top-level | complete |
| `cache/verification-backup-2026-01/misra-c/batch1_decisions/*.json` | 2 files | complete |
| `cache/verification-backup-2026-01/misra-c/batch2_decisions/*.json` | 88 files | complete |
| `cache/verification-backup-2026-01/misra-c/batch4_decisions/*.json` | 9 files | complete |
| `cache/verification-backup-2026-01/misra-c/batch5_decisions/*.json` | 4 files | complete |

### Checklist
- [x] Add `schema_version` to main mapping file (223 entries)
- [x] Add `schema_version` to backup mapping file
- [x] Add `schema_version` to backup progress file
- [x] Add `schema_version` to all 103 backup decision files
- [x] Verify JSON validity of all modified files

### Next Step
Proceed to Phase 2: Update schema definitions.

---

## Phase 2: Update Schema Definitions

Update schema files to support both v1 and v2 formats using `oneOf`.

### Schema Files to Update

| File | Status |
|------|--------|
| `schema/fls_mapping.schema.json` | complete |
| `schema/batch_report.schema.json` | complete |
| `schema/decision_file.schema.json` | complete |
| `schema/verification_progress.schema.json` | complete |

### v1 Guideline Structure (existing)

```json
{
  "schema_version": "1.0",
  "guideline_id": "Dir 4.3",
  "guideline_title": "...",
  "applicability_all_rust": "direct",
  "applicability_safe_rust": "direct",
  "fls_rationale_type": "direct_mapping",
  "confidence": "medium",
  "accepted_matches": [...],
  "rejected_matches": []
}
```

### v2 Guideline Structure (new)

```json
{
  "schema_version": "2.0",
  "guideline_id": "Dir 4.3",
  "guideline_title": "...",
  "all_rust": {
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  },
  "safe_rust": {
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  }
}
```

### v1 Decision File Structure (existing)

```json
{
  "schema_version": "1.0",
  "guideline_id": "Rule 5.8",
  "decision": "accept_with_modifications",
  "confidence": "high",
  "fls_rationale_type": "direct_mapping",
  "accepted_matches": [...],
  "rejected_matches": [],
  "search_tools_used": [...],
  "notes": "..."
}
```

### v2 Decision File Structure (new)

```json
{
  "schema_version": "2.0",
  "guideline_id": "Rule 5.8",
  "all_rust": {
    "decision": "accept_with_modifications",
    "applicability": "yes",
    "adjusted_category": "required",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "search_tools_used": [...],
    "notes": "..."
  },
  "safe_rust": {
    "decision": "accept_with_modifications",
    "applicability": "no",
    "adjusted_category": "implicit",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "search_tools_used": [...],
    "notes": "..."
  }
}
```

### v2 Progress Structure (new)

```json
{
  "schema_version": "2.0",
  "standard": "misra_c",
  "last_session": 1,
  "batches": [...],
  "guidelines": {
    "Dir 4.3": {
      "batch": 1,
      "all_rust": {
        "verified": true,
        "verified_by_session": 1
      },
      "safe_rust": {
        "verified": true,
        "verified_by_session": 1
      }
    }
  }
}
```

### Checklist
- [x] Update `fls_mapping.schema.json` with `oneOf` for v1/v2 guideline entries
- [x] Update `batch_report.schema.json` with `oneOf` for v1/v2 verification decisions
- [x] Update `decision_file.schema.json` with `oneOf` for v1/v2 decisions
- [x] Update `verification_progress.schema.json` with `oneOf` for v1/v2 progress
- [x] Validate schemas are syntactically correct

### Next Step
Proceed to Phase 3: Update tools.

---

## Phase 3: Update Tools

### New Shared Utilities

| File | Status |
|------|--------|
| `tools/src/fls_tools/shared/schema_version.py` (new) | complete |
| `tools/src/fls_tools/shared/search_id.py` (new) | complete |

### Tools to Update

| Tool | Changes | Status |
|------|---------|--------|
| `validate-standards` | Validate per-entry based on `schema_version` | complete |
| `scaffold-progress` | Generate v2 progress structure | complete |
| `verify-batch` | Generate v2 batch reports with `--schema-version` param | complete |
| `record-decision` | Complete rewrite: `--context`, `--applicability`, `--adjusted-category`; writes v2 decision files | complete |
| `validate-decisions` | Validate v1 or v2 based on `schema_version`; per-context progress | complete |
| `merge-decisions` | Handle v2 decision files; per-context merge tracking | complete |
| `check-progress` | Report per-context progress (all_rust: X/Y, safe_rust: X/Y) | complete |
| `apply-verification` | v1→v2 migration logic; writes v2 entries to mixed mapping file | complete |
| `reset-batch` | Handle v2 progress structure; `--context` flag for selective reset | complete |

### Updated `record-decision` CLI

```bash
uv run record-decision \
    --standard misra-c \
    --batch 1 \
    --guideline "Dir 4.3" \
    --context all_rust \
    --decision accept_with_modifications \
    --applicability yes \
    --adjusted-category advisory \
    --rationale-type direct_mapping \
    --confidence high \
    --search-used "uuid:tool:query:count" \
    --accept-match "fls_id:title:category:score:reason" \
    --notes "..."
```

### Checklist
- [x] Create `schema_version.py` with detection functions
- [x] Create `search_id.py` with UUID validation
- [x] Update `validate-standards`
- [x] Update `scaffold-progress`
- [x] Update `verify-batch`
- [x] Update `record-decision`
- [x] Update `validate-decisions`
- [x] Update `merge-decisions`
- [x] Update `check-progress`
- [x] Update `apply-verification`
- [x] Update `reset-batch`
- [ ] Test all tools with both v1 and v2 data

### Next Step
Phase 3 tools are complete. Proceed to Phase 4: Update verification workflow documentation.

---

## Phase 4: Update Verification Workflow

### New Protocol (8 searches per guideline)

```
1. check-guideline --guideline "Rule X.Y" --batch N

2. Verify all_rust context:
   a. search-fls-deep --guideline "Rule X.Y"
   b. search-fls --query "<C/MISRA terminology>"
   c. search-fls --query "<Rust terminology including unsafe>"
   d. search-fls --query "<unsafe-specific concerns>"
   e. record-decision --context all_rust ...

3. Verify safe_rust context:
   a. search-fls-deep --guideline "Rule X.Y"
   b. search-fls --query "<safe Rust terminology>"
   c. search-fls --query "<type system/borrow checker prevention>"
   d. search-fls --query "<safe Rust constraints>"
   e. record-decision --context safe_rust ...
```

### Updated Progress Display

```
============================================================
VERIFICATION PROGRESS: misra-c
============================================================

Current batch: 1 (High-score direct mappings)

Guideline Progress:
  Dir 4.3:  all_rust ✓  safe_rust ✓
  Dir 5.1:  all_rust ✓  safe_rust ○
  Rule 5.1: all_rust ○  safe_rust ○

Summary:
  all_rust:  5/20 verified (25%)
  safe_rust: 3/20 verified (15%)
  Both complete: 3/20 (15%)
```

### Checklist
- [x] Document new 8-search protocol in AGENTS.md
- [x] Update `AGENTS.md` verification workflow documentation
- [ ] Update `docs/verification-rerun-2026-01.md` to reference new workflow (optional)

### Next Step
Proceed to Phase 5: Update AGENTS.md.

---

## Phase 5: Update AGENTS.md

### Sections to Update

| Section | Changes | Status |
|---------|---------|--------|
| FLS Rationale Types table | Revise definitions and test questions | unchanged (still valid) |
| Verification Workflow | Document 8-search protocol | complete |
| Schema documentation | Add v2 structures | complete |
| Tool documentation | Update CLI examples | complete |
| Applicability Values | Add v2 terminology | complete |

### Updated FLS Rationale Types Table

| Type | Definition | Test Question | Applies When |
|------|------------|---------------|--------------|
| `direct_mapping` | The MISRA concern applies; Rust has equivalent constructs | "Does this safety concern exist in this Rust context?" | MISRA ADD-6 says Yes; need adapted guideline |
| `partial_mapping` | Some aspects of the MISRA concern apply | "Do only some aspects apply?" | MISRA ADD-6 says Partial |
| `rust_alternative` | Rust addresses the concern via different mechanism | "Does Rust solve this differently?" | Concern exists but Rust's approach differs |
| `rust_prevents` | Rust's design prevents the issue in this context | "Does compiler/type system prevent this?" | MISRA ADD-6 `adjusted_category` is `implicit` |
| `no_equivalent` | The C concept doesn't exist in Rust | "Does this C construct literally not exist?" | MISRA ADD-6 `adjusted_category` is `n_a` |

### Checklist
- [x] Update FLS Rationale Types table (unchanged - still valid for v2)
- [x] Update verification workflow documentation
- [x] Add v2 schema structures to documentation
- [x] Update tool CLI examples
- [x] Add v2 applicability values documentation

### Next Step
Proceed to Phase 6: Execute fresh verification.

---

## Phase 6: Execute Fresh Verification

### Pre-Verification Checklist
- [x] All tools updated and tested
- [x] Progress file reset to v2 format
- [x] Batch reports generated in v2 format

### Verification Progress

| Batch | Guidelines | all_rust | safe_rust | Both Complete |
|-------|------------|----------|-----------|---------------|
| 1 | 20 | 20/20 ✓ | 20/20 ✓ | 20/20 ✓ |
| 2 | 88 | 88/88 ✓ | 88/88 ✓ | 88/88 ✓ |
| 3 | 38 | 0/38 | 0/38 | 0/38 |
| 4 | 55 | 0/55 | 0/55 | 0/55 |
| 5 | 22 | 0/22 | 0/22 | 0/22 |
| **Total** | **223** | **108/223** | **108/223** | **108/223** |

### Session Log

| Session | Date | Batch | Guidelines Verified | Notes |
|---------|------|-------|---------------------|-------|
| 1 | 2026-01-02 | 1 | 20 (both contexts) | Initial v2 verification; fixed `migrate_v1_to_v2_entry` to include `guideline_type` |
| 2 | 2026-01-02 | 2 | 88 (both contexts) | "Not applicable" guidelines; added FLS ID validation to `record-decision`; fixed 2 hallucinated FLS IDs (Rule 9.5, Rule 18.8) |

### Next Step
After all batches verified, proceed to Phase 7: Cleanup.

---

## Phase 7: Cleanup (Post-Migration)

### Cleanup Criteria

All must be true before cleanup:
- [ ] All 223 MISRA C guidelines verified with v2 schema
- [ ] All entries in `misra_c_to_fls.json` are v2 format
- [ ] `progress.json` is v2 format
- [ ] No active batch reports or decisions in v1 format

### Cleanup Actions

- [ ] Remove v1 support from schema files (remove `oneOf`, keep only v2)
- [ ] Remove v1 code paths from tools
- [ ] Remove `detect_schema_version` fallback logic
- [ ] Update AGENTS.md to remove v1 references
- [ ] Archive or delete backup files
- [ ] Delete this migration tracking document or mark as complete

---

## Appendix: Files Modified by Phase

### Phase 1 (Tag v1)
- `coding-standards-fls-mapping/mappings/misra_c_to_fls.json`
- `cache/verification-backup-2026-01/misra-c/misra_c_to_fls.json`
- `cache/verification-backup-2026-01/misra-c/progress.json`
- `cache/verification-backup-2026-01/misra-c/batch*_decisions/*.json` (103 files)

### Phase 2 (Schemas)
- `coding-standards-fls-mapping/schema/fls_mapping.schema.json`
- `coding-standards-fls-mapping/schema/batch_report.schema.json`
- `coding-standards-fls-mapping/schema/decision_file.schema.json`
- `coding-standards-fls-mapping/schema/verification_progress.schema.json`

### Phase 3 (Tools)
- `tools/src/fls_tools/shared/schema_version.py` (new)
- `tools/src/fls_tools/standards/validation/standards.py`
- `tools/src/fls_tools/standards/validation/decisions.py`
- `tools/src/fls_tools/standards/verification/batch.py`
- `tools/src/fls_tools/standards/verification/record.py`
- `tools/src/fls_tools/standards/verification/merge.py`
- `tools/src/fls_tools/standards/verification/progress.py`
- `tools/src/fls_tools/standards/verification/apply.py`
- `tools/src/fls_tools/standards/verification/reset.py`
- `tools/src/fls_tools/standards/verification/scaffold.py`

### Phase 5 (Documentation)
- `AGENTS.md`
- `docs/verification-rerun-2026-01.md`
