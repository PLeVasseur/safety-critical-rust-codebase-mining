# Schema Migration Plan: v4.0 Paragraph-Level Requirements

This document outlines the plan to:
1. Define v4.0 schema with enforced paragraph-level match requirements
2. Create v1.2, v2.2, v3.2 "grandfather" versions for migrated data
3. Update ALL tools that interact with schema files for compatibility
4. Migrate existing data with appropriate waivers

**Created:** 2026-01-09  
**Updated:** 2026-01-09  
**Status:** In Progress

---

## Quick Progress Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Schema Definition - v4.0 and vX.2 variants | ✅ Complete |
| Phase 2 | Version Logic - Update `schema_version.py` | ✅ Complete |
| Phase 3 | Migration Tool - `migrate-to-v4` | Pending |
| Phase 4 | Core Tool Updates - `apply-verification`, `record-decision`, `merge-decisions` | Pending |
| Phase 5 | Validation Updates - `validate-standards`, `validate-decisions` | Pending |
| Phase 6 | Batch/Progress Tools - `verify-batch`, `check-progress` | Pending |
| Phase 7 | Analysis Tools - `record-outlier-analysis`, `prepare-outlier-analysis`, etc. | Pending |
| Phase 8 | Execute Migration - Run on mapping file | Pending |
| Phase 9 | Documentation - AGENTS.md updates | Pending |

---

## Table of Contents

1. [Motivation](#motivation)
2. [Schema Version Overview](#schema-version-overview)
3. [Version Compatibility Matrix](#version-compatibility-matrix)
4. [Affected Files Analysis](#affected-files-analysis)
5. [Schema Design](#schema-design)
6. [Detailed Task Breakdown](#detailed-task-breakdown)
7. [Implementation Details](#implementation-details)
8. [Rollback Strategy](#rollback-strategy)
9. [Progress Tracking](#progress-tracking)

---

## Motivation

### Problem Statement

FLS mappings must cite **paragraph-level content** (Legality Rules, UB definitions, Dynamic Semantics) 
that can be quoted in coding guidelines. Section headers like "Inline Assembly" are useless for this - 
they're just titles with no normative content.

Analysis found that:
- Verification was accepting removal of paragraph-level IDs in favor of section-level
- This loses the quotable text needed for writing coding guidelines

**Bad Example (what was being accepted):**
```
Mapping had:  fls_3fg60jblx0xb (category: -2, Legality Rule)
              "Inline assembly is written as an assembly code block that is wrapped 
               inside a macro invocation of macro core::arch::asm..."
              
Decision kept: fls_z1il3w9nulzy (category: 0, Section header)
               "Inline Assembly"
               
Analysis: "Appropriate - redundant with parent section"
```

**Why This Is Wrong:**
- The paragraph IS the useful content - it contains quotable normative text
- The section header is just a title - it contains nothing to cite
- "Redundant with parent" is backwards reasoning
- We need to cite "Inline assembly is written as..." not just "Inline Assembly"

### Solution

Enforce at the schema level that:
1. Every mapping entry must have at least one paragraph-level match (category != 0)
2. Section-level matches are allowed alongside paragraphs (not instead of)
3. Rare exceptions require explicit waiver with justification

---

## Schema Version Overview

### New Versions

| Version | Type | Description | Created By |
|---------|------|-------------|------------|
| **v1.2** | Grandfather | v1.1 + paragraph waiver for migrated data | Migration tool |
| **v2.2** | Grandfather | v2.1 + paragraph waiver for migrated data | Migration tool |
| **v3.2** | Grandfather | v3.0/v3.1 + paragraph waiver for migrated data | Migration tool |
| **v4.0** | New | Full paragraph enforcement, fresh verification | New verification workflow |

### Version Hierarchy

```
v1.0 → v1.1 (ADD-6) → v1.2 (paragraph waiver)
v2.0 → v2.1 (ADD-6) → v2.2 (paragraph waiver)
v3.0 → v3.1 (analysis) → v3.2 (paragraph waiver)
                      → v4.0 (new, enforced)
```

### Key Distinction

- **v1.2/v2.2/v3.2** = Legacy data with `paragraph_level_waiver` set to migration note
- **v4.0** = Fresh verification with enforced paragraph requirements OR explicit justified waiver

### Category Codes Reference

| Code | Name | Description | Quotable? |
|------|------|-------------|-----------|
| `0` | Section | Section header/container | **No** - just a title |
| `-1` | General | Intro text before rubrics | Sometimes |
| `-2` | Legality Rules | Compiler-enforced rules | **Yes** - normative |
| `-3` | Dynamic Semantics | Runtime behavior | **Yes** - normative |
| `-4` | Undefined Behavior | UB definitions | **Yes** - critical |
| `-5` | Implementation Requirements | Impl requirements | **Yes** - normative |
| `-6` | Implementation Permissions | Impl permissions | Sometimes |
| `-7` | Examples | Code examples | No |
| `-8` | Syntax | Grammar productions | Rarely |

**Paragraph-level** = category != 0 (everything except section headers)

---

## Version Compatibility Matrix

### Data Flow Overview

```
                              ┌──────────────────────────────────────────────┐
                              │              MAPPING FILE                     │
                              │        (misra_c_to_fls.json)                  │
                              │  v1.0 → v1.1 → v1.2 ─┐                        │
                              │  v2.0 → v2.1 → v2.2 ─┼─→ v4.0 (enforced)      │
                              │  v3.0 → v3.1 → v3.2 ─┘                        │
                              └──────────────────────────────────────────────┘
                                           ↑
                                           │ apply-verification
                                           │
┌────────────────────────┐    ┌────────────┴───────────┐    ┌──────────────────────┐
│     BATCH REPORT       │───▶│    DECISION FILES      │◀───│   record-decision    │
│   (batch*_session*.json)│    │  (batch*_decisions/*.json) │    │   (creates/updates)  │
│   v2.0, v3.0, v4.0     │    │  v2.0→v4.0, v3.0→v4.0  │    └──────────────────────┘
└────────────────────────┘    └────────────────────────┘
         ↑                               ↑
         │ verify-batch                  │ merge-decisions
         │                               │
┌────────┴───────────────┐    ┌──────────┴─────────────┐
│   PROGRESS FILE        │    │   OUTLIER ANALYSIS      │
│ (progress.json)        │    │ (outlier_analysis/*.json)│
│   v1.0, v2.0           │    │   (no schema version)   │
└────────────────────────┘    └─────────────────────────┘
```

### Tool Version Requirements

| Tool | Reads | Writes | Current Output | Needs Output |
|------|-------|--------|----------------|--------------|
| `apply-verification` | v2.0-v3.0 batch reports | v3.0 mapping entries | v3.0 | v4.0 |
| `record-decision` | v2.0-v3.1 decision files | v3.1 decision files | v3.1 | v4.0 |
| `merge-decisions` | v1.0-v3.1 decision files | Same version batch report | N/A | Handle v3.2/v4.0 |
| `verify-batch` | v2.0-v3.0 mapping entries | v2.0/v3.0 batch reports | v3.0 | v4.0 |
| `migrate-mappings` | v1.0-v3.0 entries | v1.1/v2.1 entries | v1.1/v2.1 | Add vX.2 paths |
| `validate-standards` | All versions | N/A | N/A | Paragraph validation |
| `validate-decisions` | v2.0-v3.1 | N/A | N/A | Handle v3.2/v4.0 |

### Compatibility Rules

1. **Mapping file** can contain mixed versions (v1.x, v2.x, v3.x, v4.0)
2. **Decision files** per batch should be consistent version
3. **Batch reports** version determines decision file structure
4. **Applying decisions** upgrades mapping entries to the output version

### Migration Paths

```
Existing Entry    Migration Tool      After Migration
─────────────────────────────────────────────────────
v1.0              migrate-to-v4       v1.2 + waiver (if no paragraphs)
v1.1              migrate-to-v4       v1.2 + waiver (if no paragraphs)
v2.0              migrate-to-v4       v2.2 + waiver per context
v2.1              migrate-to-v4       v2.2 + waiver per context
v3.0              migrate-to-v4       v3.2 + waiver per context
v3.1              migrate-to-v4       v3.2 + waiver per context

Fresh Verification (record-decision + apply-verification)
─────────────────────────────────────────────────────
Any version       →                   v4.0 (enforced)
```

---

## Affected Files Analysis

### Critical Updates (Would break functionality)

| File | Current State | Required Changes | Priority |
|------|---------------|------------------|----------|
| `verification/apply.py` | Outputs v3.0, accepts v2.0-v3.0 | Output v4.0, accept v3.1/v3.2/v4.0, add paragraph fields | **P0** |
| `verification/record.py` | Outputs v3.1, accepts v2.0-v3.1 | Output v4.0, add `--paragraph-level-waiver`, compute counts | **P0** |
| `verification/merge.py` | Handles v1.0-v3.1 | Add v3.2/v4.0, validate paragraph counts | **P0** |
| `verification/batch.py` | Generates v2.0/v3.0 reports | Add v4.0 generation, paragraph warnings | **P1** |

### Moderate Updates (Would cause validation warnings)

| File | Current State | Required Changes | Priority |
|------|---------------|------------------|----------|
| `validation/decisions.py` | Validates v2.0-v3.1 | Add v3.2/v4.0, paragraph validation | **P1** |
| `validation/standards.py` | Validates v1.0-v3.0 | Add paragraph coverage validation | **P1** |
| `verification/progress.py` | Displays v2.0-v3.0 | Display paragraph stats, handle v4.0 | **P2** |

### Analysis Tools

| File | Current State | Required Changes | Priority |
|------|---------------|------------------|----------|
| `analysis/shared.py` | Checks v3.1 specifically | Use `is_v3()` or add v3.2/v4.0 | **P2** |
| `analysis/record.py` | No paragraph validation | Add paragraph enforcement for outlier verdicts | **P2** |
| `analysis/prepare.py` | Shows category info | Add paragraph coverage warnings | **P2** |
| `analysis/extract.py` | Reads schema versions | Auto-handles new versions | **P3** |

### Migration Tools

| File | Current State | Required Changes | Priority |
|------|---------------|------------------|----------|
| `verification/migrate_mappings.py` | v1.0→v1.1, v2.0→v2.1 | Add v1.1→v1.2, v2.1→v2.2, v3.x→v3.2 | **P1** |
| `standards/migration/migrate_v4.py` | Does not exist | Create new tool | **P0** |

### Low Priority (Display/stats only)

| File | Current State | Required Changes | Priority |
|------|---------------|------------------|----------|
| `verification/reset.py` | Uses `is_v2_family()` | Works automatically | **None** |
| `verification/scaffold.py` | Creates progress files | No changes needed | **None** |

---

## Schema Design

### New Fields

Added to each context (`all_rust`, `safe_rust`) in v2+, or top-level in v1:

```json
{
  "paragraph_match_count": 3,
  "section_match_count": 1,
  "paragraph_level_waiver": null
}
```

**Field Definitions:**

| Field | Type | Description |
|-------|------|-------------|
| `paragraph_match_count` | integer | Count of matches with category != 0 |
| `section_match_count` | integer | Count of matches with category = 0 |
| `paragraph_level_waiver` | string \| null | If no paragraphs, explains why (null if has paragraphs) |

### v4.0 Mapping Entry Schema

```json
{
  "schema_version": "4.0",
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  "misra_add6": { ... },
  "all_rust": {
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [
      {
        "fls_id": "fls_abc123",
        "category": -2,
        "fls_title": "Type Cast Expressions",
        "score": 0.65,
        "reason": "Per FLS: 'A cast is legal when...' This directly addresses MISRA's concern."
      }
    ],
    "rejected_matches": [],
    "paragraph_match_count": 1,
    "section_match_count": 0,
    "paragraph_level_waiver": null,
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  },
  "safe_rust": { ... }
}
```

### v4.0 Decision File Schema

```json
{
  "schema_version": "4.0",
  "guideline_id": "Rule 11.1",
  "misra_add6_snapshot": { ... },
  "all_rust": {
    "decision": "accept_with_modifications",
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "analysis_summary": {
      "misra_concern": "Pointer to function casts can cause UB...",
      "rust_analysis": "FLS fls_xxx defines type cast expressions..."
    },
    "accepted_matches": [ ... ],
    "rejected_matches": [],
    "paragraph_match_count": 1,
    "section_match_count": 0,
    "paragraph_level_waiver": null,
    "search_tools_used": [ ... ],
    "notes": "..."
  },
  "safe_rust": { ... },
  "recorded_at": "2026-01-09T12:00:00Z"
}
```

### Migration Waiver Format

```
"Migrated from v{X}.{Y} on {DATE} - has {N} paragraph matches, {M} section matches - {STATUS}"
```

Where STATUS is:
- "OK" if has paragraphs
- "requires re-verification for paragraph coverage" if section-only or no matches

### Validation Rules

1. **v4.0 Entries:**
   - If `paragraph_match_count == 0` AND `paragraph_level_waiver` is null → ERROR
   - If `paragraph_level_waiver` is set, must be >= 50 characters
   - Waiver must NOT be a migration waiver (those are for vX.2)

2. **vX.2 Entries:**
   - Migration waivers are allowed (identified by "Migrated from" prefix)
   - These entries are flagged for re-verification

3. **All Entries:**
   - `paragraph_match_count` must equal actual count of matches with category != 0
   - `section_match_count` must equal actual count of matches with category = 0

---

## Detailed Task Breakdown

### Phase 1: Schema Definition ✅ Complete

| Task | Description | File | Status |
|------|-------------|------|--------|
| 1.1 | Add v1.2, v2.2, v3.2, v4.0 to `fls_mapping.schema.json` | schema/fls_mapping.schema.json | ✅ Done |
| 1.2 | Add paragraph fields to `applicability_context` def | schema/fls_mapping.schema.json | ✅ Done |
| 1.3 | Add v1.2, v2.2, v3.2, v4.0 to `decision_file.schema.json` | schema/decision_file.schema.json | ✅ Done |
| 1.4 | Add paragraph fields to decision context structures | schema/decision_file.schema.json | ✅ Done |
| 1.5 | Add v4.0 to `batch_report.schema.json` enum | schema/batch_report.schema.json | ✅ Done |
| 1.6 | Add paragraph count fields to batch guideline entries | schema/batch_report.schema.json | ✅ Done |

### Phase 2: Version Logic ✅ Complete

| Task | Description | File | Status |
|------|-------------|------|--------|
| 2.1 | Add `is_v1_2()`, `is_v2_2()`, `is_v3_2()`, `is_v4()` | shared/schema_version.py | ✅ Done |
| 2.2 | Add `is_grandfather_version()` | shared/schema_version.py | ✅ Done |
| 2.3 | Add `has_paragraph_coverage_fields()` | shared/schema_version.py | ✅ Done |
| 2.4 | Add `count_matches_by_category()` | shared/schema_version.py | ✅ Done |
| 2.5 | Add `count_entry_matches()`, `count_context_matches()` | shared/schema_version.py | ✅ Done |
| 2.6 | Add `validate_paragraph_coverage()` | shared/schema_version.py | ✅ Done |
| 2.7 | Add `build_migration_waiver()` | shared/schema_version.py | ✅ Done |

### Phase 3: Migration Tool

| Task | Description | File | Status |
|------|-------------|------|--------|
| 3.1 | Create `migrate_v4.py` module | standards/migration/migrate_v4.py | Pending |
| 3.2 | Implement `migrate_entry()` for all versions | | Pending |
| 3.3 | Implement per-context paragraph counting | | Pending |
| 3.4 | Generate migration waivers per context | | Pending |
| 3.5 | Generate migration report (Markdown) | | Pending |
| 3.6 | Add `--dry-run`, `--apply`, `--report` options | | Pending |
| 3.7 | Create backup before applying | | Pending |
| 3.8 | Add entry point to `pyproject.toml` | tools/pyproject.toml | Pending |

### Phase 4: Core Tool Updates

#### 4A: `apply-verification` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 4A.1 | Accept v3.1, v3.2, v4.0 batch reports | verification/apply.py L130-131 | Pending |
| 4A.2 | Change output version from v3.0 to v4.0 | verification/apply.py L163, L205 | Pending |
| 4A.3 | Add migration path: v3.0→v4.0, v3.1→v4.0, v3.2→v4.0 | verification/apply.py | Pending |
| 4A.4 | Compute paragraph_match_count per context | verification/apply.py | Pending |
| 4A.5 | Set paragraph_level_waiver=null (fresh verification) | verification/apply.py | Pending |
| 4A.6 | Update `migrate_v1_to_v3_entry()` → `migrate_v1_to_v4_entry()` | verification/apply.py L155-195 | Pending |
| 4A.7 | Update `migrate_v2_to_v3_entry()` → `migrate_v2_to_v4_entry()` | verification/apply.py L198-211 | Pending |
| 4A.8 | Add v4.0 to upgrade_stats tracking | verification/apply.py L273-278 | Pending |

#### 4B: `record-decision` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 4B.1 | Change `DECISION_SCHEMA_VERSION` from "3.1" to "4.0" | verification/record.py L114 | Pending |
| 4B.2 | Accept v3.2, v4.0 existing files | verification/record.py L680 | Pending |
| 4B.3 | Add `--paragraph-level-waiver` CLI option | verification/record.py | Pending |
| 4B.4 | Compute paragraph_match_count from accepted_matches | verification/record.py | Pending |
| 4B.5 | Compute section_match_count from accepted_matches | verification/record.py | Pending |
| 4B.6 | Validate paragraph coverage (error if none and no waiver) | verification/record.py | Pending |
| 4B.7 | Validate waiver length (min 50 chars) | verification/record.py | Pending |
| 4B.8 | Add paragraph fields to context decision structure | verification/record.py | Pending |

#### 4C: `merge-decisions` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 4C.1 | Accept v3.2, v4.0 decision files | verification/merge.py L196-197, L284-286 | Pending |
| 4C.2 | Validate paragraph_match_count matches actual count | verification/merge.py | Pending |
| 4C.3 | Warn if paragraph_match_count == 0 and no waiver | verification/merge.py | Pending |

### Phase 5: Validation Updates

#### 5A: `validate-standards` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 5A.1 | Add v3.1, v3.2, v4.0 to version checks | validation/standards.py L173 | Pending |
| 5A.2 | Add paragraph coverage validation for vX.2/v4.0 | validation/standards.py | Pending |
| 5A.3 | Report paragraph coverage statistics | validation/standards.py | Pending |
| 5A.4 | Flag entries needing re-verification (section-only) | validation/standards.py | Pending |

#### 5B: `validate-decisions` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 5B.1 | Add v3.2, v4.0 to version checks | validation/decisions.py L125, L196 | Pending |
| 5B.2 | Validate paragraph coverage for v4.0 decisions | validation/decisions.py | Pending |
| 5B.3 | Validate paragraph_match_count accuracy | validation/decisions.py | Pending |

### Phase 6: Batch/Progress Tools

#### 6A: `verify-batch` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 6A.1 | Accept v3.1, v3.2, v4.0 in mapping entries | verification/batch.py L373, L428 | Pending |
| 6A.2 | Add "4.0" to `--schema-version` CLI choices | verification/batch.py L654 | Pending |
| 6A.3 | Scaffold paragraph fields in v4.0 batch reports | verification/batch.py | Pending |
| 6A.4 | Add paragraph_coverage_warnings to summary | verification/batch.py | Pending |

#### 6B: `check-progress` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 6B.1 | Accept v3.1, v3.2, v4.0 in version checks | verification/progress.py L486 | Pending |
| 6B.2 | Display paragraph coverage stats | verification/progress.py | Pending |

### Phase 7: Analysis Tools

#### 7A: `analysis/shared.py` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 7A.1 | Replace `schema_version.startswith("3.1")` with proper check | analysis/shared.py L608-609 | Pending |
| 7A.2 | Add paragraph coverage to comparison flags | analysis/shared.py | Pending |

#### 7B: `record-outlier-analysis` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 7B.1 | Add `--paragraph-level-waiver-all-rust` CLI option | analysis/record.py | Pending |
| 7B.2 | Add `--paragraph-level-waiver-safe-rust` CLI option | analysis/record.py | Pending |
| 7B.3 | Validate paragraph coverage when accepting decisions | analysis/record.py | Pending |
| 7B.4 | Error if removing paragraph matches without justification | analysis/record.py | Pending |

#### 7C: `prepare-outlier-analysis` Updates

| Task | Description | File | Status |
|------|-------------|------|--------|
| 7C.1 | Show paragraph coverage stats in display | analysis/prepare.py | Pending |
| 7C.2 | Warn if decision would lose paragraph coverage | analysis/prepare.py | Pending |

### Phase 8: Execute Migration

| Task | Description | Status |
|------|-------------|--------|
| 8.1 | Backup `misra_c_to_fls.json` | Pending |
| 8.2 | Run `migrate-to-v4 --standard misra-c --dry-run` | Pending |
| 8.3 | Review migration report | Pending |
| 8.4 | Run `migrate-to-v4 --standard misra-c --apply` | Pending |
| 8.5 | Run `validate-standards --standard misra-c` | Pending |
| 8.6 | Verify paragraph coverage statistics | Pending |

### Phase 9: Documentation

| Task | Description | File | Status |
|------|-------------|------|--------|
| 9.1 | Update AGENTS.md schema version table | AGENTS.md | Pending |
| 9.2 | Add v4.0 to "Version semantics" section | AGENTS.md | Pending |
| 9.3 | Document paragraph requirement in verification workflow | AGENTS.md | Pending |
| 9.4 | Add `--paragraph-level-waiver` to record-decision docs | AGENTS.md | Pending |
| 9.5 | Document vX.2 grandfather versions | AGENTS.md | Pending |

---

## Implementation Details

### Migration Tool: `migrate-to-v4`

**Location:** `tools/src/fls_tools/standards/migration/migrate_v4.py`

**Usage:**
```bash
# Preview migration
uv run migrate-to-v4 --standard misra-c --dry-run

# Execute migration
uv run migrate-to-v4 --standard misra-c --apply

# Generate detailed report only
uv run migrate-to-v4 --standard misra-c --report
```

**Logic:**

```python
def migrate_entry(entry: dict, date: str) -> dict:
    """Migrate a single mapping entry to vX.2."""
    version = entry.get("schema_version", "1.0")
    
    # Determine new version
    if version.startswith("1"):
        new_version = "1.2"
    elif version.startswith("2"):
        new_version = "2.2"
    elif version.startswith("3"):
        new_version = "3.2"
    else:
        return entry  # Unknown, keep as-is
    
    entry["schema_version"] = new_version
    
    # Handle v1 flat structure
    if is_v1_family(entry):
        para_count, section_count = count_matches_by_category(
            entry.get("accepted_matches", [])
        )
        entry["paragraph_match_count"] = para_count
        entry["section_match_count"] = section_count
        if para_count == 0:
            entry["paragraph_level_waiver"] = build_migration_waiver(
                version, date, para_count, section_count
            )
        else:
            entry["paragraph_level_waiver"] = None
    else:
        # v2/v3 per-context structure
        for ctx in ["all_rust", "safe_rust"]:
            if ctx in entry and entry[ctx]:
                ctx_para, ctx_section = count_matches_by_category(
                    entry[ctx].get("accepted_matches", [])
                )
                entry[ctx]["paragraph_match_count"] = ctx_para
                entry[ctx]["section_match_count"] = ctx_section
                if ctx_para == 0:
                    entry[ctx]["paragraph_level_waiver"] = build_migration_waiver(
                        version, date, ctx_para, ctx_section
                    )
                else:
                    entry[ctx]["paragraph_level_waiver"] = None
    
    return entry
```

### apply-verification v4.0 Output

```python
def migrate_to_v4_entry(existing: dict, add6_data: dict | None) -> dict:
    """Migrate any version entry to v4.0 structure."""
    entry = {
        "schema_version": "4.0",
        "guideline_id": existing["guideline_id"],
        "guideline_title": existing.get("guideline_title", ""),
        "guideline_type": existing.get("guideline_type", "rule"),
    }
    
    # Add ADD-6 block
    if add6_data:
        entry["misra_add6"] = build_misra_add6_block(add6_data)
    
    # Migrate contexts
    for ctx in ["all_rust", "safe_rust"]:
        ctx_data = get_context_data(existing, ctx)  # Handles v1 flat structure
        
        para_count, section_count = count_matches_by_category(
            ctx_data.get("accepted_matches", [])
        )
        
        entry[ctx] = {
            "applicability": ctx_data.get("applicability"),
            "adjusted_category": ctx_data.get("adjusted_category"),
            "rationale_type": ctx_data.get("rationale_type"),
            "confidence": ctx_data.get("confidence", "medium"),
            "accepted_matches": ctx_data.get("accepted_matches", []),
            "rejected_matches": ctx_data.get("rejected_matches", []),
            "paragraph_match_count": para_count,
            "section_match_count": section_count,
            "paragraph_level_waiver": None,  # Fresh verification, no waiver
            "verified": False,
            "verified_by_session": None,
            "notes": ctx_data.get("notes"),
        }
    
    return entry
```

### record-decision Paragraph Validation

```python
def validate_paragraph_coverage(
    accepted_matches: list[dict],
    paragraph_waiver: str | None,
) -> list[str]:
    """Validate that decision has paragraph-level coverage."""
    errors = []
    
    paragraph_matches = [m for m in accepted_matches if m.get("category", 0) != 0]
    section_matches = [m for m in accepted_matches if m.get("category", 0) == 0]
    
    if len(paragraph_matches) == 0:
        if not paragraph_waiver:
            errors.append(
                f"No paragraph-level FLS matches (category != 0). "
                f"Found {len(section_matches)} section-level matches but these are just headers. "
                f"Must include at least one Legality Rule (-2), UB definition (-4), or Dynamic Semantics (-3). "
                f"Use --paragraph-level-waiver with justification (min 50 chars) if FLS section has no paragraph content."
            )
        elif len(paragraph_waiver) < 50:
            errors.append(
                f"--paragraph-level-waiver too short (min 50 chars, got {len(paragraph_waiver)}). "
                f"Must explain why no paragraph-level FLS content is available."
            )
    
    return errors
```

### Migration Report Format

```markdown
# v4 Migration Report: misra-c

**Date:** 2026-01-09
**Total entries:** 223

## Summary

| Category | Count | Percentage |
|----------|-------|------------|
| Has paragraph matches (OK) | 180 | 80.7% |
| Section-only (needs re-verification) | 35 | 15.7% |
| No matches (needs re-verification) | 8 | 3.6% |

## Version Distribution (After Migration)

| Version | Count |
|---------|-------|
| v1.2 | 77 |
| v2.2 | 108 |
| v3.2 | 38 |

## Per-Context Summary

| Context | Has Paragraphs | Section-Only | No Matches |
|---------|----------------|--------------|------------|
| all_rust | 175 | 40 | 8 |
| safe_rust | 168 | 47 | 8 |

## Entries Requiring Re-verification

These entries have only section-level matches and need paragraph-level content added:

| Guideline | New Version | all_rust | safe_rust |
|-----------|-------------|----------|-----------|
| Rule 1.1 | v2.2 | 0 para, 2 sec | 0 para, 2 sec |
| Dir 4.10 | v1.2 | 0 para, 1 sec | - |
| ... | ... | ... | ... |

## Entries With No Matches

| Guideline | New Version | Rationale Type |
|-----------|-------------|----------------|
| Rule X.Y | v1.2 | no_equivalent |
| ... | ... | ... |
```

---

## Rollback Strategy

If issues are found:

1. **Schema files** maintain backward compatibility - old versions still validate
2. **Migration tool** creates backup: `misra_c_to_fls.json.backup.{timestamp}`
3. **Version detection** in `schema_version.py` allows mixed versions during transition
4. **Restore command**: `cp misra_c_to_fls.json.backup.{timestamp} misra_c_to_fls.json`

---

## Progress Tracking

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Schema Definition | ✅ Complete | All schema files updated |
| Phase 2: Version Logic | ✅ Complete | schema_version.py has all utilities |
| Phase 3: Migration Tool | Pending | |
| Phase 4: Core Tool Updates | Pending | apply, record, merge |
| Phase 5: Validation Updates | Pending | validate-standards, validate-decisions |
| Phase 6: Batch/Progress Tools | Pending | verify-batch, check-progress |
| Phase 7: Analysis Tools | Pending | record-outlier-analysis, prepare, shared |
| Phase 8: Execute Migration | Pending | |
| Phase 9: Documentation | Pending | AGENTS.md |

---

## Appendix: All Affected Files

### Schema Files
- `coding-standards-fls-mapping/schema/fls_mapping.schema.json` ✅
- `coding-standards-fls-mapping/schema/decision_file.schema.json` ✅
- `coding-standards-fls-mapping/schema/batch_report.schema.json` ✅

### Shared Utilities
- `tools/src/fls_tools/shared/schema_version.py` ✅

### Verification Tools
- `tools/src/fls_tools/standards/verification/apply.py`
- `tools/src/fls_tools/standards/verification/record.py`
- `tools/src/fls_tools/standards/verification/merge.py`
- `tools/src/fls_tools/standards/verification/batch.py`
- `tools/src/fls_tools/standards/verification/progress.py`
- `tools/src/fls_tools/standards/verification/migrate_mappings.py`

### Validation Tools
- `tools/src/fls_tools/standards/validation/standards.py`
- `tools/src/fls_tools/standards/validation/decisions.py`

### Analysis Tools
- `tools/src/fls_tools/standards/analysis/shared.py`
- `tools/src/fls_tools/standards/analysis/record.py`
- `tools/src/fls_tools/standards/analysis/prepare.py`

### New Files
- `tools/src/fls_tools/standards/migration/migrate_v4.py` (to create)
- `tools/src/fls_tools/standards/migration/__init__.py` (to create)

### Configuration
- `tools/pyproject.toml` (add migrate-to-v4 entry point)

### Documentation
- `AGENTS.md`

### Data Files
- `coding-standards-fls-mapping/mappings/misra_c_to_fls.json`
