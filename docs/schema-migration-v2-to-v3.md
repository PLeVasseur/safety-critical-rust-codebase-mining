# Schema Migration Plan: v1.1/v2.1 Enrichment and v3 Verification

This document outlines the plan to:
1. Enrich existing v1.0/v2.0 entries with MISRA ADD-6 metadata (→ v1.1/v2.1)
2. Create v3.0 format for new verification decisions

**Created:** 2026-01-03  
**Last Updated:** 2026-01-03  
**Status:** Complete

---

## Quick Progress Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Foundation - `schema_version.py` and `paths.py` | ✅ Complete |
| Phase 1 | Schema Updates - Add v1.1, v2.1, v3.0 definitions | ✅ Complete |
| Phase 2 | Migration Tools - Enrich existing entries | ✅ Complete |
| Phase 3 | Core Tool Updates - Generate v3.0 going forward | ✅ Complete |
| Phase 4 | Search Enhancements - Display ADD-6 context | ✅ Complete |
| Phase 5 | Validation & Documentation | ✅ Complete |

**Status:** All migration tasks complete. v3.0 schema is now the default for verification.

---

## Table of Contents

1. [Motivation](#motivation)
2. [Schema Version Overview](#schema-version-overview)
3. [Current State Analysis](#current-state-analysis)
4. [v1.1/v2.1 Enrichment Design](#v11v21-enrichment-design)
5. [v3.0 Schema Design](#v30-schema-design)
6. [Migration Tasks](#migration-tasks)
7. [Implementation Details](#implementation-details)
8. [Rollback Strategy](#rollback-strategy)
9. [Progress Tracking](#progress-tracking)

---

## Motivation

### Problem Statement

The current v1.0 and v2.0 schemas lack valuable metadata from MISRA ADD-6 that helps verifiers and downstream consumers:

| ADD-6 Field | Current Status | Value for Verification |
|-------------|----------------|------------------------|
| `misra_category` | Not in v1/v2 | Know original MISRA severity (Required/Advisory/Mandatory) |
| `decidability` | Not in v1/v2 | Understand if static analysis can check this |
| `scope` | Not in v1/v2 | Know if analysis is per-file (STU) or system-wide |
| `rationale` (codes) | Not in v1/v2 | Understand WHY the guideline exists (UB/IDB/CQ/DC) |
| `comment` | Not in v1/v2 | MISRA's own notes about Rust applicability |

### Benefits

1. **Better Verifier Context**: Search tools can display ADD-6 metadata, helping verifiers understand guideline intent
2. **Richer Mapping Data**: Final mappings include original MISRA classification for downstream tools
3. **Audit Trail**: Captures MISRA's official Rust assessment alongside our FLS mapping
4. **Cross-Analysis**: v3.0 demarcation distinguishes fresh verification from enriched legacy data

---

## Schema Version Overview

### Version Semantics

| Version | Type | Description | Created By |
|---------|------|-------------|------------|
| **v1.0** | Original | Flat structure, no ADD-6 | Legacy |
| **v1.1** | Enriched | v1.0 + `misra_add6` block | Migration tool |
| **v2.0** | Original | Per-context structure, no ADD-6 | Previous verification |
| **v2.1** | Enriched | v2.0 + `misra_add6` block | Migration tool |
| **v3.0** | New | Per-context + ADD-6, fresh verification | New verification workflow |

### Key Distinction

- **v1.1/v2.1** = Enriched legacy data (ADD-6 added to existing entries via migration)
- **v3.0** = Fresh verification decisions (created going forward with full ADD-6 context)

This distinction enables cross-analysis:
- Identify which entries were migrated vs freshly verified
- Track verification progress over time
- Compare legacy assessments with new verification

### Version Applicability by File Type

| File | v1.0 | v1.1 | v2.0 | v2.1 | v3.0 |
|------|:----:|:----:|:----:|:----:|:----:|
| `fls_mapping.schema.json` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `decision_file.schema.json` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `batch_report.schema.json` | ✅ | - | ✅ | - | ✅ |

Batch reports don't need v1.1/v2.1 since they're generated fresh (not migrated).

---

## Current State Analysis

### Mapping File Inventory

As of 2026-01-03, `coding-standards-fls-mapping/mappings/misra_c_to_fls.json` contains:

| Schema Version | Count | Percentage | Description |
|----------------|-------|------------|-------------|
| v1.0 | 115 | 51.6% | Batches 3, 4, 5 - unverified entries |
| v2.0 | 108 | 48.4% | Batches 1, 2 - verified entries |
| **Total** | 223 | 100% | |

**Batch-to-Version Mapping:**

| Batch | Name | Current Version | After Migration |
|-------|------|-----------------|-----------------|
| 1 | High-score direct | v2.0 | v2.1 |
| 2 | Not applicable | v2.0 | v2.1 |
| 3 | Stdlib & Resources | v1.0 | v1.1 |
| 4 | Medium-score direct | v1.0 | v1.1 |
| 5 | Edge cases | v1.0 | v1.1 |

### Decision Files

No decision files currently exist in `cache/verification/`. They are deleted after verification is applied per cleanup protocol.

### ADD-6 Data Source

**File:** `coding-standards-fls-mapping/misra_rust_applicability.json`

Contains 228 guideline entries with:
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

---

## v1.1/v2.1 Enrichment Design

### Enrichment Principle

v1.1 and v2.1 are **additive** - they add a `misra_add6` block without changing existing fields.

### v1.1 Mapping Entry Structure

```json
{
  "schema_version": "1.1",
  "guideline_id": "Rule 21.3",
  "guideline_title": "The memory allocation functions...",
  "applicability_all_rust": "direct",
  "applicability_safe_rust": "not_applicable",
  "fls_rationale_type": "rust_prevents",
  "confidence": "medium",
  "accepted_matches": [...],
  "rejected_matches": [],
  
  "misra_add6": {
    "misra_category": "Required",
    "decidability": "Undecidable",
    "scope": "System",
    "rationale_codes": ["UB"],
    "applicability_all_rust": "Yes",
    "applicability_safe_rust": "No",
    "adjusted_category": "advisory",
    "comment": "Safe Rust has no direct heap allocation functions",
    "source_version": "ADD-6:2025"
  }
}
```

### v2.1 Mapping Entry Structure

```json
{
  "schema_version": "2.1",
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  
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
    "applicability": "no",
    "adjusted_category": "n_a",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 1,
    "notes": "..."
  }
}
```

### v1.1/v2.1 Decision File Structure

Decision files gain `misra_add6_snapshot`:

**v1.1 Decision File:**
```json
{
  "schema_version": "1.1",
  "guideline_id": "Rule 21.3",
  "decision": "accept_with_modifications",
  "confidence": "high",
  "fls_rationale_type": "rust_prevents",
  "accepted_matches": [...],
  "rejected_matches": [],
  "search_tools_used": [...],
  "recorded_at": "2026-01-03T...",
  
  "misra_add6_snapshot": {
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

**v2.1 Decision File:**
```json
{
  "schema_version": "2.1",
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

---

## v3.0 Schema Design

### Design Principle

v3.0 is **structurally identical to v2.1** but indicates **fresh verification** rather than enriched migration.

### v3.0 Mapping Entry Structure

```json
{
  "schema_version": "3.0",
  "guideline_id": "Rule 11.1",
  "guideline_title": "Conversions shall not be performed...",
  
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
    "applicability": "yes",
    "adjusted_category": "advisory",
    "rationale_type": "direct_mapping",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 5,
    "notes": "..."
  },
  "safe_rust": {
    "applicability": "no",
    "adjusted_category": "n_a",
    "rationale_type": "rust_prevents",
    "confidence": "high",
    "accepted_matches": [...],
    "rejected_matches": [],
    "verified": true,
    "verified_by_session": 5,
    "notes": "..."
  }
}
```

### v3.0 Decision File Structure

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

### v3.0 Batch Report Structure

```json
{
  "schema_version": "3.0",
  "batch_id": 3,
  "session_id": 5,
  "generated_date": "2026-01-03",
  "standard": "misra_c",
  "thresholds": { "section": 0.5, "paragraph": 0.55 },
  
  "guidelines": [
    {
      "guideline_id": "Rule 21.3",
      "guideline_title": "...",
      
      "misra_add6": {
        "misra_category": "Required",
        "decidability": "Undecidable",
        "scope": "System",
        "rationale_codes": ["UB"],
        "applicability_all_rust": "Yes",
        "applicability_safe_rust": "No",
        "adjusted_category": "advisory",
        "comment": "..."
      },
      
      "current_state": { /* ... */ },
      "rationale": "MISRA rationale text...",
      "similarity_data": { /* ... */ },
      "fls_content": { /* ... */ },
      "verification_decision": {
        "all_rust": { /* ... */ },
        "safe_rust": { /* ... */ }
      }
    }
  ],
  
  "applicability_changes": [],
  "summary": { /* ... */ }
}
```

---

## Migration Tasks

### Task Overview

| ID | Task | Phase | Priority | Dependencies |
|----|------|-------|----------|--------------|
| 0a | Update `schema_version.py` for v1.1/v2.1/v3.0 | 0 | High | None |
| 0b | Add `get_misra_rust_applicability_path()` to `paths.py` | 0 | High | None |
| 1a | Update `fls_mapping.schema.json` | 1 | High | None |
| 1b | Update `decision_file.schema.json` | 1 | High | None |
| 1c | Update `batch_report.schema.json` | 1 | High | None |
| 2a | Write `migrate-mappings` tool | 2 | High | 0a, 0b, 1a |
| 2b | Run migration on `misra_c_to_fls.json` | 2 | High | 2a |
| 3a | Update `batch.py` for v3.0 batch reports | 3 | High | 0a, 0b, 1c |
| 3b | Update `record.py` for v3.0 decision files | 3 | High | 0a, 1b |
| 3c | Update `apply.py` for v1.1/v2.1/v3.0 handling | 3 | High | 0a, 1a |
| 3d | Update `merge.py` for v3.0 decision files | 3 | Medium | 0a, 1b |
| 4a | Enhance `search_deep.py` with ADD-6 display | 4 | Medium | 0b |
| 4b | Enhance `search.py` with optional ADD-6 display | 4 | Low | 0b |
| 5a | Update validation tools | 5 | Medium | 1a, 1b, 1c |
| 5b | Update `AGENTS.md` documentation | 5 | High | All |
| 5c | Update this migration doc with final status | 5 | Low | All |

---

### Phase 0: Foundation

#### Task 0a: Update `schema_version.py`

**File:** `tools/src/fls_tools/shared/schema_version.py`

**Changes:**

1. Update `SchemaVersion` type:
   ```python
   SchemaVersion = Literal["1.0", "1.1", "2.0", "2.1", "3.0"]
   ```

2. Add detection functions:
   ```python
   def is_v1_1(data: Dict[str, Any]) -> bool:
       """Check if data is v1.1 format (v1 + ADD-6)."""
       return detect_schema_version(data) == "1.1"

   def is_v2_1(data: Dict[str, Any]) -> bool:
       """Check if data is v2.1 format (v2 + ADD-6)."""
       return detect_schema_version(data) == "2.1"

   def is_v3(data: Dict[str, Any]) -> bool:
       """Check if data is v3.0 format."""
       return detect_schema_version(data) == "3.0"
   ```

3. Update `get_guideline_schema_version()`:
   ```python
   def get_guideline_schema_version(guideline: Dict[str, Any]) -> SchemaVersion:
       # Explicit version field takes precedence
       if guideline.get("schema_version"):
           return guideline["schema_version"]
       
       # Heuristic detection for unversioned entries
       has_add6 = "misra_add6" in guideline
       has_per_context = "all_rust" in guideline and "safe_rust" in guideline
       has_flat = "applicability_all_rust" in guideline
       
       if has_per_context:
           return "2.1" if has_add6 else "2.0"
       if has_flat:
           return "1.1" if has_add6 else "1.0"
       
       return "1.0"  # Default
   ```

4. Add helper to check if entry has ADD-6:
   ```python
   def has_add6_data(data: Dict[str, Any]) -> bool:
       """Check if entry has misra_add6 block."""
       return "misra_add6" in data or "misra_add6_snapshot" in data
   ```

5. Export new functions in `shared/__init__.py`

#### Task 0b: Add Path Helper

**File:** `tools/src/fls_tools/shared/paths.py`

**Changes:**

Add function:
```python
def get_misra_rust_applicability_path(root: Path) -> Path:
    """Get path to MISRA ADD-6 Rust applicability JSON."""
    return get_coding_standards_dir(root) / "misra_rust_applicability.json"
```

Export in `shared/__init__.py`.

---

### Phase 1: Schema Updates

#### Task 1a: Update `fls_mapping.schema.json`

**File:** `coding-standards-fls-mapping/schema/fls_mapping.schema.json`

**Changes:**

1. Add `misra_add6` definition to `$defs`:
   ```json
   "misra_add6": {
     "type": "object",
     "description": "MISRA ADD-6 Rust applicability data",
     "required": ["misra_category", "decidability", "scope", "rationale_codes"],
     "properties": {
       "misra_category": {
         "type": "string",
         "enum": ["Required", "Advisory", "Mandatory"]
       },
       "decidability": {
         "type": "string",
         "enum": ["Decidable", "Undecidable", "n/a"]
       },
       "scope": {
         "type": "string",
         "enum": ["STU", "System", "n/a"]
       },
       "rationale_codes": {
         "type": "array",
         "items": { "type": "string", "enum": ["UB", "IDB", "CQ", "DC"] }
       },
       "applicability_all_rust": {
         "type": "string",
         "enum": ["Yes", "No", "Partial"]
       },
       "applicability_safe_rust": {
         "type": "string",
         "enum": ["Yes", "No", "Partial"]
       },
       "adjusted_category": {
         "type": "string",
         "enum": ["required", "advisory", "recommended", "disapplied", "implicit", "n_a"]
       },
       "comment": { "type": ["string", "null"] },
       "source_version": { "type": "string" }
     }
   }
   ```

2. Add `mapping_entry_v1_1` definition (v1.0 + misra_add6)

3. Add `mapping_entry_v2_1` definition (v2.0 + misra_add6)

4. Add `mapping_entry_v3` definition (same structure as v2.1, different const version)

5. Update `mappings.items.oneOf` to include all five versions

#### Task 1b: Update `decision_file.schema.json`

**File:** `coding-standards-fls-mapping/schema/decision_file.schema.json`

**Changes:**

1. Add `misra_add6_snapshot` definition (same as `misra_add6` but without `source_version`)

2. Add `decision_file_v1_1` definition (v1.0 + misra_add6_snapshot)

3. Add `decision_file_v2_1` definition (v2.0 + misra_add6_snapshot)

4. Add `decision_file_v3` definition (same structure as v2.1, different const version)

5. Update top-level `oneOf` to include all five versions

#### Task 1c: Update `batch_report.schema.json`

**File:** `coding-standards-fls-mapping/schema/batch_report.schema.json`

**Changes:**

1. Add `misra_add6` definition to `$defs`

2. Add `misra_add6` as optional property in `guideline_entry`

3. Update `schema_version` enum to include "3.0"

4. v3.0 batch reports require `misra_add6` in guideline entries

---

### Phase 2: Migration Tools

#### Task 2a: Write `migrate-mappings` Tool

**New File:** `tools/src/fls_tools/standards/verification/migrate_mappings.py`

**Purpose:** Enrich v1.0 → v1.1 and v2.0 → v2.1 by adding ADD-6 data

**Implementation:**

```python
#!/usr/bin/env python3
"""
migrate-mappings - Enrich mapping entries with MISRA ADD-6 data.

Upgrades:
  v1.0 → v1.1 (adds misra_add6 block)
  v2.0 → v2.1 (adds misra_add6 block)

Usage:
    uv run migrate-mappings --standard misra-c --dry-run
    uv run migrate-mappings --standard misra-c
"""

import argparse
import json
import sys
from pathlib import Path

from fls_tools.shared import (
    get_project_root,
    get_mapping_path,
    get_misra_rust_applicability_path,
    get_guideline_schema_version,
)


def build_misra_add6_block(add6_data: dict) -> dict:
    """Build misra_add6 block from ADD-6 source data."""
    return {
        "misra_category": add6_data.get("misra_category"),
        "decidability": add6_data.get("decidability"),
        "scope": add6_data.get("scope"),
        "rationale_codes": add6_data.get("rationale", []),
        "applicability_all_rust": add6_data.get("applicability_all_rust"),
        "applicability_safe_rust": add6_data.get("applicability_safe_rust"),
        "adjusted_category": add6_data.get("adjusted_category"),
        "comment": add6_data.get("comment"),
        "source_version": "ADD-6:2025",
    }


def migrate_entry(entry: dict, add6_all: dict) -> tuple[dict, str, str]:
    """
    Migrate a single mapping entry.
    
    Returns: (migrated_entry, old_version, new_version)
    """
    gid = entry["guideline_id"]
    old_version = get_guideline_schema_version(entry)
    
    # Already enriched?
    if old_version in ("1.1", "2.1", "3.0"):
        return entry, old_version, old_version
    
    # Get ADD-6 data
    add6 = add6_all.get(gid)
    if not add6:
        print(f"  WARNING: No ADD-6 data for {gid}, skipping", file=sys.stderr)
        return entry, old_version, old_version
    
    # Enrich
    entry["misra_add6"] = build_misra_add6_block(add6)
    
    if old_version == "1.0":
        entry["schema_version"] = "1.1"
        return entry, "1.0", "1.1"
    elif old_version == "2.0":
        entry["schema_version"] = "2.1"
        return entry, "2.0", "2.1"
    
    return entry, old_version, old_version


def main():
    parser = argparse.ArgumentParser(description="Enrich mapping entries with ADD-6 data")
    parser.add_argument("--standard", required=True, choices=["misra-c", "misra-cpp", "cert-c", "cert-cpp"])
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    
    root = get_project_root()
    
    # Load ADD-6 data
    add6_path = get_misra_rust_applicability_path(root)
    if not add6_path.exists():
        print(f"ERROR: ADD-6 data not found: {add6_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(add6_path) as f:
        add6_data = json.load(f)
    add6_all = add6_data.get("guidelines", {})
    
    # Load mapping file
    mapping_path = get_mapping_path(root, args.standard)
    with open(mapping_path) as f:
        mappings = json.load(f)
    
    # Migrate entries
    stats = {"v1.0→v1.1": 0, "v2.0→v2.1": 0, "skipped": 0, "no_add6": 0}
    
    for i, entry in enumerate(mappings.get("mappings", [])):
        migrated, old_v, new_v = migrate_entry(entry, add6_all)
        mappings["mappings"][i] = migrated
        
        if old_v == new_v:
            if "misra_add6" not in migrated:
                stats["no_add6"] += 1
            else:
                stats["skipped"] += 1
        elif old_v == "1.0":
            stats["v1.0→v1.1"] += 1
        elif old_v == "2.0":
            stats["v2.0→v2.1"] += 1
    
    # Report
    print(f"\nMigration Summary for {args.standard}:")
    print(f"  v1.0 → v1.1: {stats['v1.0→v1.1']}")
    print(f"  v2.0 → v2.1: {stats['v2.0→v2.1']}")
    print(f"  Already enriched (skipped): {stats['skipped']}")
    print(f"  Missing ADD-6 data: {stats['no_add6']}")
    
    if args.dry_run:
        print("\nDRY RUN - no changes written")
    else:
        with open(mapping_path, "w") as f:
            json.dump(mappings, f, indent=2)
        print(f"\nWrote changes to {mapping_path}")


if __name__ == "__main__":
    main()
```

**Entry Point:** Add to `pyproject.toml`:
```toml
migrate-mappings = "fls_tools.standards.verification.migrate_mappings:main"
```

#### Task 2b: Run Migration

After implementing Task 2a:

```bash
cd tools
uv run migrate-mappings --standard misra-c --dry-run  # Preview
uv run migrate-mappings --standard misra-c            # Apply
```

Expected result:
- 115 entries: v1.0 → v1.1
- 108 entries: v2.0 → v2.1

---

### Phase 3: Core Tool Updates

#### Task 3a: Update `batch.py`

**File:** `tools/src/fls_tools/standards/verification/batch.py`

**Changes:**

1. Import ADD-6 helpers from `shared`

2. Load ADD-6 data at start:
   ```python
   def load_add6_data(root: Path) -> dict:
       path = get_misra_rust_applicability_path(root)
       if not path.exists():
           print(f"WARNING: ADD-6 data not found: {path}", file=sys.stderr)
           return {}
       with open(path) as f:
           data = json.load(f)
       return data.get("guidelines", {})
   ```

3. Include `misra_add6` in each guideline entry

4. Change default `--schema-version` to "3.0"

5. Always generate v3.0 batch reports (remove v1.0/v2.0 options)

#### Task 3b: Update `record.py`

**File:** `tools/src/fls_tools/standards/verification/record.py`

**Changes:**

1. Load ADD-6 data for the guideline

2. Include `misra_add6_snapshot` in v3.0 decision files

3. Always generate v3.0 decision files

4. Warn if ADD-6 data unavailable but don't fail

#### Task 3c: Update `apply.py`

**File:** `tools/src/fls_tools/standards/verification/apply.py`

**Changes:**

1. Handle reading v1.0, v1.1, v2.0, v2.1, v3.0 entries

2. Always write v3.0 entries when applying verification

3. Load ADD-6 data and include in output

4. Track upgrade statistics:
   ```
   Applied verification:
     v1.0 → v3.0: 0
     v1.1 → v3.0: 38
     v2.0 → v3.0: 0
     v2.1 → v3.0: 0
     v3.0 updated: 0
   ```

5. Implement ADD-6 mismatch detection:
   ```python
   def check_add6_mismatch(snapshot: dict, current: dict, guideline_id: str) -> list[str]:
       """Compare ADD-6 snapshot with current data, return list of differences."""
       mismatches = []
       for field in ["misra_category", "applicability_all_rust", "applicability_safe_rust", "adjusted_category"]:
           snap_val = snapshot.get(field)
           curr_val = current.get(field)
           if snap_val != curr_val:
               mismatches.append(f"  {field}: \"{snap_val}\" (snapshot) vs \"{curr_val}\" (current)")
       return mismatches
   ```
   
   Warn on mismatch but continue applying.

#### Task 3d: Update `merge.py`

**File:** `tools/src/fls_tools/standards/verification/merge.py`

**Changes:**

1. Detect v3.0 decision files

2. Preserve `misra_add6_snapshot` when merging to batch report

3. Validate ADD-6 snapshot matches batch report's `misra_add6` (warn on mismatch)

---

### Phase 4: Search Enhancements

#### Task 4a: Enhance `search_deep.py`

**File:** `tools/src/fls_tools/standards/verification/search_deep.py`

**Changes:**

1. Load ADD-6 data for the guideline

2. Display ADD-6 context in output header with full rationale code expansion:
   ```
   ======================================================================
   DEEP SEARCH RESULTS: Rule 21.3
   ======================================================================
   Title: The memory allocation and deallocation functions...

   MISRA ADD-6 Context:
     Original Category: Required
     Decidability: Undecidable
     Scope: System
     Rationale: UB (Undefined Behaviour), DC (Design Consideration)
     All Rust: Yes → advisory
     Safe Rust: No → implicit
     Comment: Safe Rust has no direct heap allocation functions
   
   Embeddings used: 5
   ...
   ```

3. Add `--no-add6` flag to suppress ADD-6 display

4. Include ADD-6 in JSON output mode (`--json`)

#### Task 4b: Enhance `search.py`

**File:** `tools/src/fls_tools/standards/verification/search.py`

**Changes:**

1. Add optional `--for-guideline "Rule X.Y"` parameter

2. When provided, display ADD-6 context as header before results

3. No change to search behavior (still uses query string)

---

### Phase 5: Validation & Documentation

#### Task 5a: Update Validation Tools

**Files:**
- `tools/src/fls_tools/standards/validation/standards.py`
- `tools/src/fls_tools/standards/validation/decisions.py`

**Changes:**

1. Support v1.1, v2.1, v3.0 schema validation

2. Validate `misra_add6` presence for v1.1/v2.1/v3.0 entries

3. Warn on entries missing ADD-6 data

#### Task 5b: Update `AGENTS.md`

**File:** `AGENTS.md`

**Changes:**

1. Update schema version references throughout

2. Document v1.1/v2.1/v3.0 schema structures

3. Update example JSON snippets

4. Document migration workflow

5. Update `--schema-version` CLI options

6. Update search tool output examples with ADD-6 context

#### Task 5c: Update This Document

Mark all tasks complete, update session log.

---

## Implementation Details

### Implementation Order

```
Phase 0: Foundation
    ├── Task 0a: schema_version.py
    └── Task 0b: paths.py
    
Phase 1: Schema Updates (can run in parallel)
    ├── Task 1a: fls_mapping.schema.json
    ├── Task 1b: decision_file.schema.json
    └── Task 1c: batch_report.schema.json

Phase 2: Migration
    ├── Task 2a: Write migrate-mappings tool
    └── Task 2b: Run migration
    
Phase 3: Core Tools (after Phase 2)
    ├── Task 3a: batch.py
    ├── Task 3b: record.py
    ├── Task 3c: apply.py
    └── Task 3d: merge.py

Phase 4: Search Enhancements (can run in parallel with Phase 3)
    ├── Task 4a: search_deep.py
    └── Task 4b: search.py
    
Phase 5: Validation & Documentation (after all)
    ├── Task 5a: Validation tools
    ├── Task 5b: AGENTS.md
    └── Task 5c: This document
```

### Backwards Compatibility

1. **Reading:** All tools handle v1.0, v1.1, v2.0, v2.1, v3.0

2. **Writing:** 
   - Migration tool: v1.0 → v1.1, v2.0 → v2.1
   - All other tools: Always write v3.0

3. **Validation:** JSON Schema uses `oneOf` to accept all versions

### Testing Checklist

**Phase 0 Tests:**
- [ ] `schema_version.py` detects all five versions correctly
- [ ] `is_v1_1()`, `is_v2_1()`, `is_v3()` functions work
- [ ] `has_add6_data()` correctly identifies enriched entries
- [ ] `get_misra_rust_applicability_path()` returns correct path

**Phase 1 Tests:**
- [ ] v1.1 mapping entries validate against schema
- [ ] v2.1 mapping entries validate against schema
- [ ] v3.0 mapping entries validate against schema
- [ ] v1.1/v2.1/v3.0 decision files validate against schema
- [ ] v3.0 batch reports validate against schema
- [ ] Mixed-version mapping file validates (all entries pass)

**Phase 2 Tests:**
- [ ] `migrate-mappings --dry-run` reports correct counts
- [ ] `migrate-mappings` correctly enriches v1.0 → v1.1
- [ ] `migrate-mappings` correctly enriches v2.0 → v2.1
- [ ] Already-enriched entries are skipped
- [ ] Missing ADD-6 data is warned but doesn't fail

**Phase 3 Tests:**
- [ ] `verify-batch` produces v3.0 batch reports with `misra_add6`
- [ ] `record-decision` creates v3.0 decision files with `misra_add6_snapshot`
- [ ] `apply-verification` handles v1.1/v2.1 inputs correctly
- [ ] `apply-verification` writes v3.0 outputs
- [ ] `apply-verification` warns on ADD-6 mismatches
- [ ] `merge-decisions` handles v3.0 decision files

**Phase 4 Tests:**
- [ ] `search-fls-deep` displays ADD-6 context with expanded rationale codes
- [ ] `search-fls-deep --no-add6` suppresses ADD-6 display
- [ ] `search-fls --for-guideline` displays ADD-6 context

**Phase 5 Tests:**
- [ ] Validation tools accept v1.1/v2.1/v3.0 entries
- [ ] Validation tools warn on missing ADD-6 data

---

## Rollback Strategy

If issues arise during migration:

1. **Schema Rollback:** Revert schema changes; enriched entries become invalid until re-reverted

2. **Data Rollback:** Use git to revert mapping file changes

3. **Tool Rollback:** Revert code changes; tools continue supporting v1.0/v2.0

### Checkpoints

Create git tags before each phase:
- `pre-schema-v1.1-v2.1-v3` (before Phase 0)
- `pre-migration-enrichment` (before Phase 2)
- `post-migration-enrichment` (after Phase 2)

---

## Progress Tracking

### Phase 0: Foundation

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 0a | Update `schema_version.py` | ✅ Complete | Added v1.1/v2.1/v3.0 detection, `build_misra_add6_block()`, `check_add6_mismatch()` |
| 0b | Add path helper to `paths.py` | ✅ Complete | `get_misra_rust_applicability_path()` already existed |

### Phase 1: Schema Updates

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 1a | Update `fls_mapping.schema.json` | ✅ Complete | Added v1.1, v2.1, v3.0 definitions with `misra_add6` |
| 1b | Update `decision_file.schema.json` | ✅ Complete | Added v1.1, v2.1, v3.0 definitions with `misra_add6_snapshot` |
| 1c | Update `batch_report.schema.json` | ✅ Complete | Added v3.0, `misra_add6` in guideline entry |

### Phase 2: Migration Tools

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 2a | Write `migrate-mappings` tool | ✅ Complete | Created `migrate_mappings.py`, entry point added |
| 2b | Run migration on `misra_c_to_fls.json` | ✅ Complete | 115 v1.0→v1.1, 108 v2.0→v2.1, 223/223 have ADD-6 |

### Phase 3: Core Tool Updates

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 3a | Update `batch.py` | ✅ Complete | Generates v3.0 batch reports with `misra_add6` |
| 3b | Update `record.py` | ✅ Complete | Creates v3.0 decision files with `misra_add6_snapshot` |
| 3c | Update `apply.py` | ✅ Complete | Upgrades all entries to v3.0, tracks version stats, warns on ADD-6 mismatch |
| 3d | Update `merge.py` | ✅ Complete | Handles v2.0/v2.1/v3.0 decision files, preserves ADD-6 snapshot |

### Phase 4: Search Enhancements

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 4a | Enhance `search_deep.py` | ✅ Complete | Displays ADD-6 with expanded rationale codes, `--no-add6` flag |
| 4b | Enhance `search.py` | ✅ Complete | Added `--for-guideline` parameter for ADD-6 display |

### Phase 5: Validation & Documentation

| Task | Description | Status | Notes |
|------|-------------|--------|-------|
| 5a | Update validation tools | ✅ Complete | `standards.py` and `decisions.py` handle v1.1/v2.1/v3.0 |
| 5b | Update `AGENTS.md` | ✅ Complete | Added v3.0 structure, version semantics table, search tool ADD-6 docs |
| 5c | Update this migration doc | ✅ Complete | This update |

### Session Log

| Session | Date | Tasks Completed | Notes |
|---------|------|-----------------|-------|
| 1 | 2026-01-03 | Plan revision | Revised plan from v3-only to v1.1/v2.1/v3.0 scheme |
| 2 | 2026-01-03 | Phase 0, 1, 2 | Foundation, schemas, migration tool, ran migration |
| 3 | 2026-01-03 | Phase 3, 4, 5a | Core tools, search enhancements, validation tools |
| 4 | 2026-01-03 | Phase 5b, 5c | AGENTS.md documentation, migration doc finalization |

---

## Appendix: Rationale Code Reference

| Code | Full Name | Description |
|------|-----------|-------------|
| `UB` | Undefined Behaviour | Guideline addresses C undefined behavior |
| `IDB` | Implementation-defined Behaviour | Guideline addresses implementation-defined behavior |
| `CQ` | Code Quality | Guideline improves code quality/maintainability |
| `DC` | Design Consideration | Guideline addresses design/architecture concerns |

---

## Appendix: ADD-6 Field Reference

| Field | Values | Description |
|-------|--------|-------------|
| `misra_category` | Required, Advisory, Mandatory | Original MISRA C category |
| `decidability` | Decidable, Undecidable, n/a | Can static analysis check this? |
| `scope` | STU, System, n/a | Single translation unit or system-wide analysis |
| `rationale_codes` | [UB, IDB, CQ, DC] | Why guideline exists (array) |
| `applicability_all_rust` | Yes, No, Partial | MISRA's all-Rust applicability |
| `applicability_safe_rust` | Yes, No, Partial | MISRA's safe-Rust applicability |
| `adjusted_category` | required, advisory, recommended, disapplied, implicit, n_a | MISRA's Rust-adjusted category |
| `comment` | string | MISRA's Rust-specific notes |
| `source_version` | string | ADD-6 version (e.g., "ADD-6:2025") |
