# Schema Migration Plan: v2 to v3

This document outlines the plan to migrate from v1/v2 guideline decisions to v3 format, bringing additional metadata from `misra_rust_applicability.json` (MISRA ADD-6) into the verification workflow.

**Created:** 2026-01-03  
**Status:** Not Started

---

## Quick Progress Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Foundation (Task 0) | ⬜ Not Started |
| Phase 1 | Schema Updates (Tasks 1-3) | ⬜ Not Started |
| Phase 2 | Core Tool Updates (Tasks 4-6) | ⬜ Not Started |
| Phase 3 | Supporting Updates (Tasks 7-9) | ⬜ Not Started |
| Phase 4 | Migration & Documentation (Tasks 10-12) | ⬜ Not Started |

**Next Action:** Start Phase 0 - Update `schema_version.py` with v3 support.

---

## Table of Contents

1. [Motivation](#motivation)
2. [Current State Analysis](#current-state-analysis)
3. [Mixed Schema Version Handling](#mixed-schema-version-handling)
4. [v3 Schema Design](#v3-schema-design)
5. [Migration Tasks](#migration-tasks)
6. [Implementation Details](#implementation-details)
7. [Rollback Strategy](#rollback-strategy)
8. [Progress Tracking](#progress-tracking)

---

## Motivation

### Problem Statement

The current v2 schema captures per-context verification decisions but does **not** include valuable metadata from MISRA ADD-6 that would help verifiers and downstream consumers:

| ADD-6 Field | Current Status | Value for Verification |
|-------------|----------------|------------------------|
| `misra_category` | Not in v2 | Know original MISRA severity (Required/Advisory/Mandatory) |
| `decidability` | Not in v2 | Understand if static analysis can check this |
| `scope` | Not in v2 | Know if analysis is per-file (STU) or system-wide |
| `rationale` (codes) | Not in v2 | Understand WHY the guideline exists (UB/IDB/CQ/DC) |
| `comment` | Not in v2 | MISRA's own notes about Rust applicability |

### Benefits of v3

1. **Better Verifier Context**: Search tools can display ADD-6 metadata, helping verifiers understand guideline intent
2. **Richer Mapping Data**: Final mappings include original MISRA classification for downstream tools
3. **Audit Trail**: Captures MISRA's official Rust assessment alongside our FLS mapping
4. **Filtering Capability**: Can filter guidelines by decidability, scope, or rationale codes

---

## Current State Analysis

### v1 Schema (Legacy)

```json
{
  "schema_version": "1.0",
  "guideline_id": "Rule 11.1",
  "guideline_title": "...",
  "applicability_all_rust": "direct",
  "applicability_safe_rust": "not_applicable",
  "fls_rationale_type": "direct_mapping",
  "confidence": "medium",
  "accepted_matches": [...],
  "rejected_matches": []
}
```

**Issues**: Flat structure, shared rationale type, legacy applicability values.

### v2 Schema (Current)

```json
{
  "schema_version": "2.0",
  "guideline_id": "Rule 11.1",
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
  "safe_rust": { /* same structure */ }
}
```

**Improvements over v1**: Per-context verification, simplified applicability values, adjusted_category per context.

**Gaps**: Missing `misra_category`, `decidability`, `scope`, `rationale` codes, `comment` from ADD-6.

### ADD-6 Data Structure

```json
{
  "Rule 22.8": {
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale": ["DC"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "disapplied",
    "comment": "only accessible through unsafe extern \"C\""
  }
}
```

**Key ADD-6 Fields:**

| Field | Description |
|-------|-------------|
| `misra_category` | **Original** MISRA C category (Required/Advisory/Mandatory) - the C-world classification |
| `adjusted_category` | MISRA's **adjusted** category for Rust - MISRA's own Rust assessment |
| `applicability_all_rust` | MISRA's assessment: does this apply to all Rust (including unsafe)? |
| `applicability_safe_rust` | MISRA's assessment: does this apply to safe Rust only? |

---

## Mixed Schema Version Handling

### Current State Inventory

As of 2026-01-03, the mapping file `coding-standards-fls-mapping/mappings/misra_c_to_fls.json` contains a **mixed state**:

| Schema Version | Count | Percentage | Description |
|----------------|-------|------------|-------------|
| v1.0 | 115 | 51.6% | Batches 3, 4, 5 - unverified entries |
| v2.0 | 108 | 48.4% | Batches 1, 2 - verified entries |
| v3.0 | 0 | 0% | Not yet created |
| **Total** | 223 | 100% | |

**Batch-to-Version Mapping:**

| Batch | Name | Version | Status |
|-------|------|---------|--------|
| 1 | High-score direct | v2.0 | Completed |
| 2 | Not applicable | v2.0 | Completed |
| 3 | Stdlib & Resources | v1.0 | Pending |
| 4 | Medium-score direct | v1.0 | Pending |
| 5 | Edge cases | v1.0 | Pending |

### Tool Behavior: Reading vs Writing

The v3 migration follows an asymmetric approach:

| Operation | v1 Support | v2 Support | v3 Support |
|-----------|------------|------------|------------|
| **Reading** existing data | ✅ Must handle | ✅ Must handle | ✅ Must handle |
| **Writing** new data | ❌ Never create | ❌ Never create | ✅ Always create |

**Reading (All Tools):** Tools that read mapping files, batch reports, or decision files must detect and handle all three schema versions. This is required because:
- v1 entries exist in the mapping file (unverified batches 3-5)
- v2 entries exist in the mapping file (verified batches 1-2)
- v3 entries will be created by new verification work

**Writing (All Tools):** Tools that create new data must always create v3 format:
- `verify-batch` → creates v3 batch reports
- `record-decision` → creates v3 decision files
- `apply-verification` → writes v3 mapping entries

### Schema Version Detection Updates

**File:** `tools/src/fls_tools/shared/schema_version.py`

The existing module handles v1/v2 detection. It must be extended for v3:

```python
SchemaVersion = Literal["1.0", "2.0", "3.0"]

def is_v3(data: Dict[str, Any]) -> bool:
    """Check if data is v3.0 format."""
    return detect_schema_version(data) == "3.0"

def get_guideline_schema_version(guideline: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a guideline entry.
    
    v1.0 indicators: has applicability_all_rust, applicability_safe_rust fields
    v2.0 indicators: has all_rust, safe_rust nested objects, no misra_add6
    v3.0 indicators: has all_rust, safe_rust nested objects, AND misra_add6
    """
    if guideline.get("schema_version"):
        return guideline["schema_version"]
    
    # Heuristic detection for unversioned entries
    if "misra_add6" in guideline:
        return "3.0"
    if "all_rust" in guideline and "safe_rust" in guideline:
        return "2.0"
    if "applicability_all_rust" in guideline:
        return "1.0"
    
    return "1.0"  # Default to v1
```

### Converting v1 Entries in Batch Reports

When `verify-batch` generates a batch report for v1 entries (batches 3-5), it should convert the `current_state` to v3 structure:

**v1 Entry in Mapping File:**
```json
{
  "schema_version": "1.0",
  "guideline_id": "Rule 21.3",
  "applicability_all_rust": "direct",
  "applicability_safe_rust": "not_applicable",
  "fls_rationale_type": "rust_prevents",
  "confidence": "medium",
  "accepted_matches": [...]
}
```

**Converted `current_state` in v3 Batch Report:**
```json
{
  "current_state": {
    "schema_version": "1.0",
    "all_rust": {
      "applicability": "yes",
      "adjusted_category": null,
      "rationale_type": "rust_prevents",
      "confidence": "medium",
      "accepted_matches": [...],
      "rejected_matches": [],
      "verified": false
    },
    "safe_rust": {
      "applicability": "no",
      "adjusted_category": null,
      "rationale_type": "rust_prevents",
      "confidence": "medium",
      "accepted_matches": [...],
      "rejected_matches": [],
      "verified": false
    }
  },
  "misra_add6": {
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale_codes": ["UB"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "advisory",
    "comment": "..."
  }
}
```

**Conversion Rules (v1 → v3 current_state):**

| v1 Field | v3 Field | Conversion |
|----------|----------|------------|
| `applicability_all_rust: "direct"` | `all_rust.applicability: "yes"` | `direct` → `yes`, `not_applicable` → `no`, `partial` → `partial` |
| `applicability_safe_rust` | `safe_rust.applicability` | Same conversion |
| `fls_rationale_type` | Both contexts' `rationale_type` | Copied to both |
| `confidence` | Both contexts' `confidence` | Copied to both |
| `accepted_matches` | Both contexts' `accepted_matches` | Copied to both |
| `rejected_matches` | Both contexts' `rejected_matches` | Copied to both |
| *(not in v1)* | `adjusted_category` | Set to `null` (verifier must decide) |
| *(not in v1)* | `verified` | Set to `false` |

**MISRA ADD-6 Data:** The `misra_add6` block is populated from `misra_rust_applicability.json`, providing:
- MISRA's official Rust applicability assessments
- Starting point values for `adjusted_category` (verifier may confirm or override)

### Indefinite Mixed State

The mapping file will contain mixed v1/v2/v3 entries for an indefinite period:

- **v1 entries** remain until their batch is verified
- **v2 entries** can be upgraded to v3 via `migrate-v3` tool (optional)
- **v3 entries** are created by new verification work

**Validation:** The schema allows all three versions via `oneOf` in the JSON Schema.

**No forced migration:** There is no target date to migrate all entries to v3. Migration happens organically as:
1. Pending batches are verified → v1 → v3
2. Optionally, verified batches are migrated → v2 → v3

---

## v3 Schema Design

### Design Principles

1. **Additive**: v3 extends v2 structure; does not remove v2 fields
2. **Dual Assessment**: Captures both MISRA's official assessment AND our FLS-based verification
3. **Source Attribution**: Clearly distinguish MISRA ADD-6 data from our verification decisions
4. **Per-Context Reference**: Each context includes MISRA's assessment for easy comparison
5. **Immutable Source Data**: ADD-6 metadata is copied at verification time, not referenced

### Dual Assessment Model

v3 captures **two independent assessments** for each guideline:

| Assessment | Source | Purpose |
|------------|--------|---------|
| **MISRA's Assessment** | ADD-6 document | Official MISRA position on Rust applicability |
| **Our Assessment** | FLS-based verification | Our analysis linking guideline to specific FLS sections |

These assessments may **agree or differ**. Both are recorded for:
1. Audit trail of MISRA's official position
2. Documentation of our independent analysis
3. Identification of cases where we disagree with MISRA
4. Downstream tooling that needs either or both perspectives

### Proposed v3 Mapping Entry Structure

```json
{
  "schema_version": "3.0",
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  "guideline_type": "rule",
  
  "misra_add6": {
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale_codes": ["UB", "DC"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "disapplied",
    "comment": "Safe Rust type system prevents arbitrary pointer casts",
    "source_version": "ADD-6:2025"
  },
  
  "all_rust": {
    "misra_applicability": "Yes",
    "misra_adjusted_category": "disapplied",
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
    "misra_applicability": "No",
    "misra_adjusted_category": "implicit",
    "applicability": "no",
    "adjusted_category": "n_a",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "Safe Rust type system prevents this issue entirely"
  }
}
```

### Proposed v3 Batch Report Entry Structure

```json
{
  "guideline_id": "Rule 11.1",
  "guideline_title": "...",
  
  "misra_add6": {
    "misra_category": "Required",
    "decidability": "Undecidable", 
    "scope": "System",
    "rationale_codes": ["UB", "DC"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "disapplied",
    "comment": "..."
  },
  
  "current_state": { /* existing mapping state */ },
  "rationale": "MISRA rationale text...",
  "similarity_data": { /* ... */ },
  "fls_content": { /* ... */ },
  "verification_decision": {
    "all_rust": { /* ... */ },
    "safe_rust": { /* ... */ }
  }
}
```

### Proposed v3 Decision File Structure

```json
{
  "schema_version": "3.0",
  "guideline_id": "Rule 11.1",
  
  "misra_add6_snapshot": {
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale_codes": ["UB", "DC"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "disapplied",
    "comment": "..."
  },
  
  "all_rust": { /* context decision */ },
  "safe_rust": { /* context decision */ },
  "recorded_at": "2026-01-03T..."
}
```

### New Fields Summary

**Guideline-Level Fields (in `misra_add6` block):**

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `misra_add6.misra_category` | enum | ADD-6 | Original MISRA C category: `Required`, `Advisory`, `Mandatory` |
| `misra_add6.decidability` | enum | ADD-6 | `Decidable`, `Undecidable`, `n/a` |
| `misra_add6.scope` | enum | ADD-6 | `STU` (single translation unit), `System`, `n/a` |
| `misra_add6.rationale_codes` | array | ADD-6 | Why guideline exists: `UB`, `IDB`, `CQ`, `DC` |
| `misra_add6.applicability_all_rust` | enum | ADD-6 | MISRA's all-Rust applicability: `Yes`, `No`, `Partial` |
| `misra_add6.applicability_safe_rust` | enum | ADD-6 | MISRA's safe-Rust applicability: `Yes`, `No`, `Partial` |
| `misra_add6.adjusted_category` | enum | ADD-6 | MISRA's adjusted category for Rust |
| `misra_add6.comment` | string | ADD-6 | MISRA's Rust-specific notes |
| `misra_add6.source_version` | string | Generated | Track ADD-6 version used |

**Per-Context Fields (in `all_rust` and `safe_rust` blocks):**

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `misra_applicability` | enum | ADD-6 | MISRA's applicability for this context (for reference) |
| `misra_adjusted_category` | enum | ADD-6 | MISRA's adjusted category for this context (for reference) |
| `applicability` | enum | Verification | **Our** applicability assessment |
| `adjusted_category` | enum | Verification | **Our** adjusted category (may differ from MISRA) |

**Assessment Comparison:**

The per-context structure enables direct comparison:

```
all_rust:
  MISRA says:  applicability = "Yes",  adjusted_category = "advisory"
  We say:      applicability = "yes",  adjusted_category = "advisory"
  → Agreement ✓

safe_rust:
  MISRA says:  applicability = "No",   adjusted_category = "implicit"
  We say:      applicability = "no",   adjusted_category = "n_a"
  → Partial agreement (both say N/A, but different category reasoning)
```

---

## Migration Tasks

### Task Overview

| ID | Task | Priority | Complexity | Dependencies |
|----|------|----------|------------|--------------|
| 0 | Update `schema_version.py` for v3 detection | High | Low | None |
| 1 | Update `fls_mapping.schema.json` for v3 | High | Low | None |
| 2 | Update `batch_report.schema.json` for v3 | High | Low | None |
| 3 | Update `decision_file.schema.json` for v3 | High | Low | None |
| 4 | Modify `batch.py` to include ADD-6 data | High | Medium | 0, 1, 2 |
| 5 | Modify `record.py` to capture ADD-6 snapshot | High | Medium | 0, 3 |
| 6 | Modify `apply.py` to write v3 mappings | High | Medium | 0, 1 |
| 7 | Modify `merge.py` to handle v3 decisions | Medium | Low | 0, 3 |
| 8 | Enhance `search_deep.py` with ADD-6 display | Medium | Low | None |
| 9 | Enhance `search.py` with optional ADD-6 context | Low | Low | None |
| 10 | Write `migrate-v3` tool for existing data | Medium | Medium | 0, 1 |
| 11 | Update AGENTS.md documentation | High | Low | All |
| 12 | Update validation tools | Medium | Low | 0, 1-3 |

### Detailed Task Breakdown

---

### Task 0: Update `schema_version.py` for v3 Detection

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/shared/schema_version.py`

**Changes**:

1. Update `SchemaVersion` type to include "3.0":
   ```python
   SchemaVersion = Literal["1.0", "2.0", "3.0"]
   ```

2. Add `is_v3()` function:
   ```python
   def is_v3(data: Dict[str, Any]) -> bool:
       """Check if data is v3.0 format."""
       return detect_schema_version(data) == "3.0"
   ```

3. Update `get_guideline_schema_version()` for v3 detection:
   ```python
   def get_guideline_schema_version(guideline: Dict[str, Any]) -> SchemaVersion:
       if guideline.get("schema_version"):
           return guideline["schema_version"]
       
       # Heuristic detection for unversioned entries
       if "misra_add6" in guideline:
           return "3.0"
       if "all_rust" in guideline and "safe_rust" in guideline:
           return "2.0"
       if "applicability_all_rust" in guideline:
           return "1.0"
       
       return "1.0"  # Default to v1
   ```

4. Add v1-to-v3 conversion helper:
   ```python
   def convert_v1_to_v3_current_state(v1_entry: dict, add6_data: dict | None) -> dict:
       """
       Convert a v1 mapping entry to v3 current_state structure for batch reports.
       
       This creates a v3-shaped current_state from v1 data, used when generating
       batch reports for v1 entries.
       """
       return {
           "schema_version": "1.0",  # Preserve original version for reference
           "all_rust": {
               "misra_applicability": add6_data.get("applicability_all_rust") if add6_data else None,
               "misra_adjusted_category": add6_data.get("adjusted_category") if add6_data else None,
               "applicability": convert_v1_applicability_to_v2(v1_entry.get("applicability_all_rust", "direct")),
               "adjusted_category": None,  # Verifier must decide
               "rationale_type": v1_entry.get("fls_rationale_type"),
               "confidence": v1_entry.get("confidence", "medium"),
               "accepted_matches": v1_entry.get("accepted_matches", []),
               "rejected_matches": v1_entry.get("rejected_matches", []),
               "verified": False,
           },
           "safe_rust": {
               "misra_applicability": add6_data.get("applicability_safe_rust") if add6_data else None,
               "misra_adjusted_category": add6_data.get("adjusted_category") if add6_data else None,
               "applicability": convert_v1_applicability_to_v2(v1_entry.get("applicability_safe_rust", "direct")),
               "adjusted_category": None,
               "rationale_type": v1_entry.get("fls_rationale_type"),
               "confidence": v1_entry.get("confidence", "medium"),
               "accepted_matches": v1_entry.get("accepted_matches", []),
               "rejected_matches": v1_entry.get("rejected_matches", []),
               "verified": False,
           },
       }
   ```

5. Add path helper to `shared/paths.py`:
   ```python
   def get_misra_rust_applicability_path(root: Path) -> Path:
       """Get path to MISRA ADD-6 Rust applicability JSON."""
       return get_coding_standards_dir(root) / "misra_rust_applicability.json"
   ```

6. Export new functions in `shared/__init__.py`

---

### Task 1: Update `fls_mapping.schema.json` for v3

**Status**: [ ] Not Started

**File**: `coding-standards-fls-mapping/schema/fls_mapping.schema.json`

**Changes**:

1. Add `misra_add6` object definition to `$defs`:
   ```json
   "misra_add6": {
     "type": "object",
     "description": "MISRA ADD-6 Rust applicability data for this guideline",
     "properties": {
       "misra_category": {
         "type": "string",
         "enum": ["Required", "Advisory", "Mandatory"],
         "description": "Original MISRA C category"
       },
       "decidability": {
         "type": "string", 
         "enum": ["Decidable", "Undecidable", "n/a"],
         "description": "Whether static analysis can check this guideline"
       },
       "scope": {
         "type": "string",
         "enum": ["STU", "System", "n/a"],
         "description": "Analysis scope: STU (single translation unit) or System"
       },
       "rationale_codes": {
         "type": "array",
         "items": {
           "type": "string",
           "enum": ["UB", "IDB", "CQ", "DC"]
         },
         "description": "Why this guideline exists: UB/IDB/CQ/DC"
       },
       "applicability_all_rust": {
         "type": "string",
         "enum": ["Yes", "No", "Partial"],
         "description": "MISRA's assessment: applies to all Rust?"
       },
       "applicability_safe_rust": {
         "type": "string",
         "enum": ["Yes", "No", "Partial"],
         "description": "MISRA's assessment: applies to safe Rust?"
       },
       "adjusted_category": {
         "type": "string",
         "enum": ["required", "advisory", "recommended", "disapplied", "implicit", "n_a"],
         "description": "MISRA's adjusted category for Rust"
       },
       "comment": { 
         "type": ["string", "null"],
         "description": "MISRA's Rust-specific notes"
       },
       "source_version": { 
         "type": "string",
         "description": "ADD-6 version identifier"
       }
     },
     "required": ["misra_category", "decidability", "scope", "rationale_codes"]
   }
   ```

2. Update `applicability_context` definition to add per-context MISRA fields:
   ```json
   "applicability_context": {
     "type": "object",
     "required": ["applicability", "rationale_type"],
     "properties": {
       "misra_applicability": {
         "type": ["string", "null"],
         "enum": ["Yes", "No", "Partial", null],
         "description": "MISRA's applicability for this context (from ADD-6, for reference)"
       },
       "misra_adjusted_category": {
         "type": ["string", "null"],
         "enum": ["required", "advisory", "recommended", "disapplied", "implicit", "n_a", null],
         "description": "MISRA's adjusted category for this context (from ADD-6, for reference)"
       },
       "applicability": {
         "type": "string",
         "enum": ["yes", "no", "partial"],
         "description": "OUR applicability assessment"
       },
       "adjusted_category": {
         "type": ["string", "null"],
         "enum": ["required", "advisory", "recommended", "disapplied", "implicit", "n_a", null],
         "description": "OUR adjusted category (may differ from MISRA)"
       },
       // ... existing fields: rationale_type, confidence, accepted_matches, etc.
     }
   }
   ```

3. Add `mapping_entry_v3` definition:
   ```json
   "mapping_entry_v3": {
     "type": "object",
     "description": "v3.0 format: Per-context structure with MISRA ADD-6 metadata",
     "required": ["schema_version", "guideline_id", "guideline_title", "guideline_type", "misra_add6", "all_rust", "safe_rust"],
     "properties": {
       "schema_version": {
         "type": "string",
         "const": "3.0"
       },
       "guideline_id": { "type": "string" },
       "guideline_title": { "type": "string" },
       "guideline_type": {
         "type": "string",
         "enum": ["rule", "directive", "recommendation"]
       },
       "misra_add6": { "$ref": "#/$defs/misra_add6" },
       "all_rust": { "$ref": "#/$defs/applicability_context" },
       "safe_rust": { "$ref": "#/$defs/applicability_context" }
     }
   }
   ```

4. Update `mappings.items.oneOf` to include v3:
   ```json
   "items": {
     "oneOf": [
       { "$ref": "#/$defs/mapping_entry_v1" },
       { "$ref": "#/$defs/mapping_entry_v2" },
       { "$ref": "#/$defs/mapping_entry_v3" }
     ]
   }
   ```

---

### Task 2: Update `batch_report.schema.json` for v3

**Status**: [ ] Not Started

**File**: `coding-standards-fls-mapping/schema/batch_report.schema.json`

**Changes**:

1. Add `misra_add6` to guideline entry properties (same structure as Task 1, minus `source_version`)
2. Update `schema_version` enum to include "3.0"

---

### Task 3: Update `decision_file.schema.json` for v3

**Status**: [ ] Not Started

**File**: `coding-standards-fls-mapping/schema/decision_file.schema.json`

**Changes**:

1. Add `misra_add6_snapshot` property (same structure as Task 1)
2. Update `schema_version` enum to include "3.0"
3. Make `misra_add6_snapshot` required for v3 decision files

---

### Task 4: Modify `batch.py` to Include ADD-6 Data

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/standards/verification/batch.py`

**Changes**:

1. Import new helpers:
   ```python
   from fls_tools.shared import (
       get_misra_rust_applicability_path,
       get_guideline_schema_version,
       convert_v1_to_v3_current_state,
       convert_v1_applicability_to_v2,
   )
   ```

2. Add function to load ADD-6 data:
   ```python
   def load_add6_data(root: Path) -> dict:
       """Load MISRA ADD-6 Rust applicability data."""
       path = get_misra_rust_applicability_path(root)
       if not path.exists():
           print(f"WARNING: ADD-6 data not found: {path}", file=sys.stderr)
           return {}
       with open(path) as f:
           data = json.load(f)
       return data.get("guidelines", {})
   ```

3. Add function to build `misra_add6` block:
   ```python
   def build_misra_add6_block(add6: dict | None) -> dict | None:
       """Build misra_add6 block from ADD-6 data."""
       if not add6:
           return None
       return {
           "misra_category": add6.get("misra_category"),
           "decidability": add6.get("decidability"),
           "scope": add6.get("scope"),
           "rationale_codes": add6.get("rationale", []),
           "applicability_all_rust": add6.get("applicability_all_rust"),
           "applicability_safe_rust": add6.get("applicability_safe_rust"),
           "adjusted_category": add6.get("adjusted_category"),
           "comment": add6.get("comment"),
       }
   ```

4. Update `build_guideline_entry()` to handle v1/v2/v3 and include ADD-6:
   ```python
   def build_guideline_entry(
       data: dict,
       guideline_id: str,
       add6_data: dict,  # New parameter
       section_threshold: float,
       paragraph_threshold: float,
       schema_version: SchemaVersion = "3.0",
   ) -> dict:
       mapping = get_mapping(data, guideline_id)
       mapping_version = get_guideline_schema_version(mapping)
       add6 = add6_data.get(guideline_id)
       
       # Build current_state based on mapping version
       if mapping_version == "1.0":
           # Convert v1 to v3 structure for display
           current_state = convert_v1_to_v3_current_state(mapping, add6)
       else:
           # v2 or v3 - use as-is but add MISRA reference fields if missing
           current_state = build_current_state_from_v2_or_v3(mapping, add6)
       
       return {
           "guideline_id": guideline_id,
           "guideline_title": mapping.get("guideline_title", ""),
           "misra_add6": build_misra_add6_block(add6),
           "current_state": current_state,
           "rationale": get_rationale(data, guideline_id),
           "similarity_data": get_similarity_data(...),
           "fls_content": extract_fls_content(...),
           "verification_decision": build_scaffolded_v3_decision(add6),
       }
   ```

5. Update scaffolded decision to include MISRA reference fields:
   ```python
   def build_scaffolded_v3_context_decision(add6: dict | None, context: str) -> dict:
       """Build a scaffolded v3 context decision structure."""
       misra_field = "applicability_all_rust" if context == "all_rust" else "applicability_safe_rust"
       return {
           "decision": None,
           "misra_applicability": add6.get(misra_field) if add6 else None,
           "misra_adjusted_category": add6.get("adjusted_category") if add6 else None,
           "applicability": None,
           "adjusted_category": None,
           "rationale_type": None,
           "confidence": None,
           "accepted_matches": [],
           "rejected_matches": [],
           "search_tools_used": [],
           "notes": None,
       }
   ```

6. Update CLI:
   - Change `--schema-version` default from "2.0" to "3.0"
   - Remove "1.0" and "2.0" as valid choices (always generate v3)
   
7. Warn if ADD-6 data is missing for a guideline

---

### Task 5: Modify `record.py` to Capture ADD-6 Snapshot

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/standards/verification/record.py`

**Changes**:

1. Load ADD-6 data at decision recording time:
   ```python
   from fls_tools.shared import get_misra_rust_applicability_path
   
   def load_add6_for_guideline(root: Path, guideline_id: str) -> dict | None:
       path = get_misra_rust_applicability_path(root)
       if not path.exists():
           return None
       with open(path) as f:
           data = json.load(f)
       return data.get("guidelines", {}).get(guideline_id)
   ```

2. Include ADD-6 snapshot in v3 decision files:
   ```python
   def build_v3_decision_file(guideline_id: str, add6_data: dict | None) -> dict:
       return {
           "schema_version": "3.0",
           "guideline_id": guideline_id,
           "misra_add6_snapshot": {
               "misra_category": add6_data.get("misra_category") if add6_data else None,
               "decidability": add6_data.get("decidability") if add6_data else None,
               "scope": add6_data.get("scope") if add6_data else None,
               "rationale_codes": add6_data.get("rationale", []) if add6_data else [],
               "applicability_all_rust": add6_data.get("applicability_all_rust") if add6_data else None,
               "applicability_safe_rust": add6_data.get("applicability_safe_rust") if add6_data else None,
               "adjusted_category": add6_data.get("adjusted_category") if add6_data else None,
               "comment": add6_data.get("comment") if add6_data else None,
           } if add6_data else None,
           "all_rust": build_scaffolded_context(),
           "safe_rust": build_scaffolded_context(),
           "recorded_at": None,
       }
   ```

3. Add `--schema-version` parameter (default "3.0")

4. Warn if ADD-6 data unavailable but don't fail

---

### Task 6: Modify `apply.py` to Write v3 Mappings

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/standards/verification/apply.py`

**Changes**:

1. Import new helpers:
   ```python
   from fls_tools.shared import (
       get_misra_rust_applicability_path,
       get_guideline_schema_version,
       is_v1, is_v2, is_v3,
   )
   ```

2. Load ADD-6 data at start:
   ```python
   def load_add6_data(root: Path) -> dict:
       path = get_misra_rust_applicability_path(root)
       if not path.exists():
           return {}
       with open(path) as f:
           data = json.load(f)
       return data.get("guidelines", {})
   ```

3. Replace existing `migrate_v1_to_v2_entry()` with `build_v3_entry()`:
   ```python
   def build_v3_entry(
       guideline_id: str,
       guideline_title: str,
       guideline_type: str,
       add6: dict | None,
   ) -> dict:
       """
       Build a fresh v3 mapping entry structure.
       
       This completely replaces any v1 or v2 content - only the guideline
       metadata is preserved. The context blocks are empty/scaffolded.
       """
       return {
           "schema_version": "3.0",
           "guideline_id": guideline_id,
           "guideline_title": guideline_title,
           "guideline_type": guideline_type,
           "misra_add6": {
               "misra_category": add6.get("misra_category") if add6 else None,
               "decidability": add6.get("decidability") if add6 else None,
               "scope": add6.get("scope") if add6 else None,
               "rationale_codes": add6.get("rationale", []) if add6 else [],
               "applicability_all_rust": add6.get("applicability_all_rust") if add6 else None,
               "applicability_safe_rust": add6.get("applicability_safe_rust") if add6 else None,
               "adjusted_category": add6.get("adjusted_category") if add6 else None,
               "comment": add6.get("comment") if add6 else None,
               "source_version": "ADD-6:2025",
           } if add6 else None,
           "all_rust": {
               "misra_applicability": add6.get("applicability_all_rust") if add6 else None,
               "misra_adjusted_category": add6.get("adjusted_category") if add6 else None,
               "applicability": None,
               "adjusted_category": None,
               "rationale_type": None,
               "confidence": None,
               "accepted_matches": [],
               "rejected_matches": [],
               "verified": False,
               "verified_by_session": None,
               "notes": None,
           },
           "safe_rust": {
               "misra_applicability": add6.get("applicability_safe_rust") if add6 else None,
               "misra_adjusted_category": add6.get("adjusted_category") if add6 else None,
               "applicability": None,
               "adjusted_category": None,
               "rationale_type": None,
               "confidence": None,
               "accepted_matches": [],
               "rejected_matches": [],
               "verified": False,
               "verified_by_session": None,
               "notes": None,
           },
       }
   ```

4. Update `update_mappings_v2()` to `update_mappings()` handling v1/v2/v3:
   ```python
   def update_mappings(
       mappings: dict,
       report: dict,
       add6_all: dict,  # All ADD-6 data
       session_id: int,
       apply_applicability_changes: bool,
   ) -> tuple[dict, int, int, int]:
       """
       Update mappings with verified decisions.
       
       Returns:
           (updated_mappings, v1_upgraded, v2_upgraded, v3_updated)
       """
       v1_upgraded = 0
       v2_upgraded = 0
       v3_updated = 0
       
       for g in report["guidelines"]:
           gid = g["guideline_id"]
           vd = g.get("verification_decision")
           existing = mapping_lookup.get(gid)
           existing_version = get_guideline_schema_version(existing)
           add6 = add6_all.get(gid)
           
           # Always create fresh v3 entry (complete replacement)
           entry = build_v3_entry(
               gid,
               existing.get("guideline_title", ""),
               existing.get("guideline_type", "rule"),
               add6,
           )
           
           # Apply verified context decisions
           for context in ["all_rust", "safe_rust"]:
               ctx_decision = vd.get(context, {})
               if ctx_decision.get("decision") is not None:
                   apply_v3_decision_to_context(entry, context, ctx_decision, session_id)
           
           # Track what was upgraded
           if existing_version == "1.0":
               v1_upgraded += 1
           elif existing_version == "2.0":
               v2_upgraded += 1
           else:
               v3_updated += 1
           
           mappings["mappings"][idx] = entry
       
       return mappings, v1_upgraded, v2_upgraded, v3_updated
   ```

5. Update summary output:
   ```python
   print(f"  v1 entries upgraded to v3: {v1_upgraded}", file=sys.stderr)
   print(f"  v2 entries upgraded to v3: {v2_upgraded}", file=sys.stderr)
   print(f"  v3 entries updated: {v3_updated}", file=sys.stderr)
   ```

---

### Task 7: Modify `merge.py` to Handle v3 Decisions

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/standards/verification/merge.py`

**Changes**:

1. Detect v3 decision files by `schema_version`
2. Preserve `misra_add6_snapshot` when merging to batch report
3. Validate ADD-6 snapshot matches current ADD-6 data (warn on mismatch)

---

### Task 8: Enhance `search_deep.py` with ADD-6 Display

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/standards/verification/search_deep.py`

**Changes**:

1. Load ADD-6 data for the guideline:
   ```python
   add6 = load_add6_for_guideline(root, guideline_id)
   ```

2. Display ADD-6 context in output header:
   ```
   ======================================================================
   DEEP SEARCH RESULTS: Rule 21.3
   ======================================================================
   Title: The memory allocation and deallocation functions...

   MISRA ADD-6 Context:
     Original Category: Required
     Decidability: Undecidable
     Scope: System
     Rationale: UB (Undefined Behavior), DC (Design Consideration)
     All Rust: Yes -> advisory
     Safe Rust: No -> implicit
     Comment: Safe Rust has no direct heap allocation functions
   
   Embeddings used: 5
   ...
   ```

3. Add `--no-add6` flag to suppress ADD-6 display

4. Add ADD-6 to JSON output mode

---

### Task 9: Enhance `search.py` with Optional ADD-6 Context

**Status**: [ ] Not Started

**File**: `tools/src/fls_tools/standards/verification/search.py`

**Changes**:

1. Add optional `--for-guideline "Rule X.Y"` parameter
2. When provided, display ADD-6 context as header before results
3. No change to search behavior (still uses query, not guideline embeddings)

---

### Task 10: Write v2-to-v3 Migration Script

**Status**: [ ] Not Started

**New File**: `tools/src/fls_tools/standards/verification/migrate_v3.py`

**Purpose**: Migrate existing v2 mapping entries to v3 format by adding ADD-6 data

**Implementation**:

```python
#!/usr/bin/env python3
"""
migrate_v3.py - Migrate v2 mapping entries to v3 format.

Adds misra_add6 metadata from misra_rust_applicability.json to existing
mapping entries.

Usage:
    uv run migrate-v3 --standard misra-c --dry-run
    uv run migrate-v3 --standard misra-c
"""

def migrate_mapping_to_v3(root: Path, standard: str, dry_run: bool) -> None:
    # Load mapping file
    mapping_path = get_mapping_path(root, standard)
    mapping = load_json(mapping_path)
    
    # Load ADD-6 data
    add6_data = load_add6_data(root)
    
    migrated = 0
    skipped = 0
    missing_add6 = []
    
    for guideline_id, entry in mapping.get("guidelines", {}).items():
        if entry.get("schema_version") == "3.0":
            skipped += 1
            continue
        
        add6 = add6_data.get(guideline_id)
        if not add6:
            missing_add6.append(guideline_id)
            continue
        
        # Upgrade to v3
        entry["schema_version"] = "3.0"
        entry["misra_add6"] = {
            "misra_category": add6.get("misra_category"),
            "decidability": add6.get("decidability"),
            "scope": add6.get("scope"),
            "rationale_codes": add6.get("rationale", []),
            "applicability_all_rust": add6.get("applicability_all_rust"),
            "applicability_safe_rust": add6.get("applicability_safe_rust"),
            "adjusted_category": add6.get("adjusted_category"),
            "comment": add6.get("comment"),
            "source_version": "ADD-6:2025",
        }
        migrated += 1
    
    if dry_run:
        print(f"DRY RUN - Would migrate {migrated} entries to v3")
        print(f"  Already v3: {skipped}")
        print(f"  Missing ADD-6 data: {len(missing_add6)}")
        if missing_add6:
            for gid in missing_add6[:5]:
                print(f"    - {gid}")
            if len(missing_add6) > 5:
                print(f"    ... and {len(missing_add6) - 5} more")
    else:
        save_json(mapping_path, mapping)
        print(f"Migrated {migrated} entries to v3")
```

**Entry Point**: Add to `pyproject.toml`:
```toml
migrate-v3 = "fls_tools.standards.verification.migrate_v3:main"
```

---

### Task 11: Update AGENTS.md Documentation

**Status**: [ ] Not Started

**File**: `AGENTS.md`

**Changes**:

1. Update schema version references throughout
2. Document v3 schema structure
3. Update example JSON snippets
4. Add migration instructions
5. Document new `--schema-version 3.0` options
6. Update search tool output examples with ADD-6 context

---

### Task 12: Update Validation Tools

**Status**: [ ] Not Started

**Files**: 
- `tools/src/fls_tools/standards/validation/standards.py`
- `tools/src/fls_tools/standards/validation/decisions.py`

**Changes**:

1. Support v3 schema validation
2. Validate `misra_add6` presence for v3 entries
3. Warn on ADD-6 data inconsistencies

---

## Implementation Details

### Implementation Order

```
Phase 0: Foundation (Task 0)
    └── schema_version.py - v3 detection, conversion helpers, path helpers
        (Must be done first - all other tasks depend on this)

Phase 1: Schema Updates (Tasks 1-3)
    ├── Can be done in parallel after Phase 0
    └── JSON Schema definitions only

Phase 2: Core Tool Updates (Tasks 4-6)
    ├── batch.py (Task 4) - requires Task 0, 1, 2
    │   └── Converts v1 current_state to v3 structure in batch reports
    ├── record.py (Task 5) - requires Task 0, 3
    └── apply.py (Task 6) - requires Task 0, 1
        └── Handles v1→v3 and v2→v3 upgrades

Phase 3: Supporting Updates (Tasks 7-9)
    ├── merge.py (Task 7) - requires Task 0, 3
    ├── search_deep.py (Task 8)
    └── search.py (Task 9)

Phase 4: Migration & Documentation (Tasks 10-12)
    ├── migrate-v3 tool (Task 10) - for batch upgrading existing v2 entries
    ├── AGENTS.md (Task 11)
    └── Validation tools (Task 12)
```

### Backwards Compatibility

1. **Schema Version Detection**: All tools detect schema version via `get_guideline_schema_version()` and handle v1/v2/v3 appropriately

2. **Mixed Versions Supported Indefinitely**: 
   - Mapping file can contain v1, v2, AND v3 entries simultaneously
   - No forced migration timeline
   - JSON Schema uses `oneOf` to validate all three formats

3. **Reading vs Writing Asymmetry**:
   - **Reading**: Tools must handle all three versions
   - **Writing**: Tools always create v3 (never v1 or v2)

4. **Upgrade Paths**:
   | From | To | Trigger |
   |------|-----|---------|
   | v1 | v3 | `apply-verification` processes the entry |
   | v2 | v3 | `apply-verification` or `migrate-v3` |
   | v3 | v3 | `apply-verification` updates in place |

5. **Validation**: 
   - v1 entries remain valid per existing schema
   - v2 entries remain valid per existing schema  
   - v3 entries require `misra_add6` block and per-context MISRA reference fields

### Testing Checklist

**Phase 0 Tests:**
- [ ] `schema_version.py` detects v1, v2, v3 correctly
- [ ] `is_v1()`, `is_v2()`, `is_v3()` functions work
- [ ] `convert_v1_to_v3_current_state()` produces valid structure
- [ ] `get_misra_rust_applicability_path()` returns correct path

**Phase 1 Tests:**
- [ ] v3 mapping schema validates v3 entries
- [ ] v3 batch report schema validates v3 reports
- [ ] v3 decision file schema validates v3 decisions
- [ ] Mixed v1/v2/v3 mapping file validates (all entries pass)

**Phase 2 Tests:**
- [ ] `verify-batch` produces v3 batch reports
- [ ] `verify-batch` converts v1 entries to v3 structure in `current_state`
- [ ] `verify-batch` includes `misra_add6` block from ADD-6 data
- [ ] `record-decision` creates v3 decision files with `misra_add6_snapshot`
- [ ] `apply-verification` upgrades v1 entries to v3
- [ ] `apply-verification` upgrades v2 entries to v3
- [ ] `apply-verification` updates existing v3 entries

**Phase 3 Tests:**
- [ ] `merge-decisions` handles v3 decision files
- [ ] `search-fls-deep` displays ADD-6 context in output
- [ ] `search-fls` with `--for-guideline` displays ADD-6 context

**Phase 4 Tests:**
- [ ] `migrate-v3 --dry-run` reports correct counts
- [ ] `migrate-v3` upgrades v2 entries to v3 with ADD-6 data
- [ ] Validation tools accept v3 entries
- [ ] Validation tools warn on missing ADD-6 data

---

## Rollback Strategy

If issues arise during migration:

1. **Schema Rollback**: Remove v3 from schema enum; v3 entries become invalid
2. **Data Rollback**: Use git to revert mapping file changes
3. **Tool Rollback**: Revert code changes; tools continue supporting v2

### Checkpoints

Before each phase, create a git tag:
- `pre-v3-schema-update`
- `pre-v3-tool-update`
- `pre-v3-migration`

---

## Progress Tracking

### Phase 0: Foundation

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 0 | Update `schema_version.py` | ⬜ Not Started | Add v3 detection, conversion helpers |

**Phase 0 Checkpoint:** Create git tag `pre-v3-foundation` before starting.

### Phase 1: Schema Updates

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 1 | Update `fls_mapping.schema.json` | ⬜ Not Started | Add `misra_add6` object, v3 entry type, per-context MISRA fields |
| 2 | Update `batch_report.schema.json` | ⬜ Not Started | Add `misra_add6` to guideline entry |
| 3 | Update `decision_file.schema.json` | ⬜ Not Started | Add `misra_add6_snapshot` to v3 |

**Phase 1 Checkpoint:** Create git tag `pre-v3-schema-update` before starting.

### Phase 2: Core Tool Updates

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 4 | Modify `batch.py` | ⬜ Not Started | Load ADD-6, include in batch reports |
| 5 | Modify `record.py` | ⬜ Not Started | Capture ADD-6 snapshot in decisions |
| 6 | Modify `apply.py` | ⬜ Not Started | Write v3 mapping entries with ADD-6 |

**Phase 2 Checkpoint:** Create git tag `pre-v3-tool-update` before starting.

### Phase 3: Supporting Updates

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 7 | Modify `merge.py` | ⬜ Not Started | Handle v3 decision files |
| 8 | Enhance `search_deep.py` | ⬜ Not Started | Display ADD-6 context in output |
| 9 | Enhance `search.py` | ⬜ Not Started | Optional `--for-guideline` ADD-6 display |

### Phase 4: Migration & Documentation

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 10 | Write `migrate_v3.py` | ⬜ Not Started | Migrate existing v2 entries to v3 |
| 11 | Update `AGENTS.md` | ⬜ Not Started | Document v3 schema and workflows |
| 12 | Update validation tools | ⬜ Not Started | Support v3 schema validation |

**Phase 4 Checkpoint:** Create git tag `pre-v3-migration` before running migration.

### Session Log

| Session | Date | Tasks Completed | Notes |
|---------|------|-----------------|-------|
| - | - | - | No work started yet |

---

## Open Questions

1. **ADD-6 Version Tracking**: Should we track which ADD-6 version was used? (Currently proposed: `source_version: "ADD-6:2025"`)

2. **Mismatch Handling**: What if ADD-6 data changes between decision recording and apply? Options:
   - Warn only (current proposal)
   - Fail and require re-verification
   - Auto-update snapshot

3. **Missing ADD-6 Data**: For guidelines not in ADD-6, should we:
   - Allow v3 with null `misra_add6`? (current proposal)
   - Require v2 for such guidelines?
   - Synthesize placeholder ADD-6 data?

4. **Rationale Code Display**: Should search tools explain rationale codes? E.g., "UB (Undefined Behavior)" vs just "UB"

---

## Appendix: Rationale Code Reference

| Code | Full Name | Description |
|------|-----------|-------------|
| `UB` | Undefined Behaviour | Guideline addresses C undefined behavior |
| `IDB` | Implementation-defined Behaviour | Guideline addresses implementation-defined behavior |
| `CQ` | Code Quality | Guideline improves code quality/maintainability |
| `DC` | Design Consideration | Guideline addresses design/architecture concerns |
