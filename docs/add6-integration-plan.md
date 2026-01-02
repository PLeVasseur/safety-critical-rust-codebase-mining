# ADD-6 Integration Plan

**Created:** 2026-01-03
**Status:** Planning

This document tracks the integration of MISRA C:2025 Addendum 6 (ADD-6) Rust applicability data into the verification workflow.

---

## Background

We extracted ADD-6 data from the MISRA PDF and stored it in `coding-standards-fls-mapping/misra_rust_applicability.json`. This data contains official MISRA classifications for how each guideline applies to Rust, including:

- `applicability_all_rust` / `applicability_safe_rust` - Yes/No/Partial
- `adjusted_category` - required/advisory/recommended/disapplied/implicit/n_a
- `rationale` - Why the rule exists: UB, IDB, CQ, DC (can be multiple)
- `decidability` - Decidable/Undecidable/n/a
- `scope` - STU/System/n/a
- `comment` - MISRA's explanation for Rust

**Problem:** This data is not being used effectively during verification. The LLM must manually enter applicability and category values without seeing MISRA's official classifications, leading to potential inconsistencies.

---

## Goals

1. **Surface ADD-6 data** during verification so the LLM can see MISRA's official classifications
2. **Track both classifications** - MISRA's ADD-6 classification AND our LLM-derived classification
3. **Require explicit disagreement** - If LLM disagrees with ADD-6, require a flag and justification
4. **Use rationale types** to guide search strategy (UB rules → safety-critical FLS; DC rules → design pattern FLS)

---

## Schema Version Progression

| Version | Description |
|---------|-------------|
| v1.0 | Flat structure, single applicability |
| v2.0 | Per-context structure (all_rust, safe_rust) |
| **v3.0** | Per-context + ADD-6 integration + dual classification |

---

## Phase 1: Schema Updates (v3.0)

### 1.1 Batch Report Schema (`batch_report.schema.json`)

**Add `add6_data` to `guideline_entry`:**

```json
"add6_data": {
  "type": "object",
  "description": "MISRA ADD-6 official Rust applicability data",
  "properties": {
    "rationale": {
      "type": "array",
      "items": { "type": "string", "enum": ["UB", "IDB", "CQ", "DC"] },
      "description": "Why the rule exists (Undefined Behavior, Implementation-Defined, Code Quality, Design Considerations)"
    },
    "decidability": {
      "type": "string",
      "enum": ["Decidable", "Undecidable", "n/a"]
    },
    "scope": {
      "type": "string", 
      "enum": ["STU", "System", "n/a"]
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
    "comment": {
      "type": ["string", "null"]
    }
  }
}
```

**Tasks:**
- [ ] Update `batch_report.schema.json` to v3.0 with `add6_data` field
- [ ] Add `schema_version: "3.0"` enum option

### 1.2 Decision File Schema (`decision_file.schema.json`)

**Add ADD-6 agreement tracking to context decisions:**

```json
"add6_agreement": {
  "type": "object",
  "description": "Tracks alignment between LLM decision and MISRA ADD-6",
  "required": ["agrees_with_add6"],
  "properties": {
    "agrees_with_add6": {
      "type": "boolean",
      "description": "Whether this decision agrees with MISRA ADD-6 classification"
    },
    "add6_applicability": {
      "type": "string",
      "enum": ["Yes", "No", "Partial"],
      "description": "MISRA ADD-6's applicability value for reference"
    },
    "add6_adjusted_category": {
      "type": "string",
      "enum": ["required", "advisory", "recommended", "disapplied", "implicit", "n_a"],
      "description": "MISRA ADD-6's adjusted category for reference"
    },
    "disagreement_rationale": {
      "type": ["string", "null"],
      "description": "Required if agrees_with_add6 is false - explains why LLM disagrees"
    }
  }
}
```

**Tasks:**
- [ ] Update `decision_file.schema.json` to v3.0
- [ ] Add `add6_agreement` to `context_decision_complete`
- [ ] Make `disagreement_rationale` required when `agrees_with_add6: false`

### 1.3 FLS Mapping Schema (`fls_mapping.schema.json`)

**Add dual classification to v3.0 context:**

```json
"applicability_context_v3": {
  "type": "object",
  "required": ["applicability", "rationale_type", "add6"],
  "properties": {
    "applicability": { ... },          // LLM's classification
    "adjusted_category": { ... },      // LLM's classification
    "rationale_type": { ... },         // LLM's classification
    "add6": {
      "type": "object",
      "description": "MISRA ADD-6's official classification",
      "properties": {
        "applicability": { "type": "string", "enum": ["Yes", "No", "Partial"] },
        "adjusted_category": { "type": "string", "enum": ["required", "advisory", "recommended", "disapplied", "implicit", "n_a"] },
        "rationale": { "type": "array", "items": { "type": "string", "enum": ["UB", "IDB", "CQ", "DC"] } }
      }
    },
    "agrees_with_add6": {
      "type": "boolean",
      "description": "Whether LLM classification agrees with ADD-6"
    },
    "disagreement_rationale": {
      "type": ["string", "null"],
      "description": "Explanation if LLM disagrees with ADD-6"
    },
    ...
  }
}
```

**Tasks:**
- [ ] Update `fls_mapping.schema.json` with `mapping_entry_v3`
- [ ] Add dual classification structure
- [ ] Update `statistics` to include disagreement counts

---

## Phase 2: Tool Updates

### 2.1 `verify-batch` (batch.py)

**Changes:**
1. Load `misra_rust_applicability.json` at startup
2. For each guideline, include `add6_data` in the entry
3. Output ADD-6 classification prominently in batch report

**New function:**
```python
def load_add6_data(root: Path, standard: str) -> dict:
    """Load MISRA ADD-6 applicability data."""
    if standard != "misra-c":
        return {}  # ADD-6 only exists for MISRA C
    path = get_coding_standards_dir(root) / "misra_rust_applicability.json"
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get("guidelines", {})

def get_add6_for_guideline(add6_data: dict, guideline_id: str) -> dict | None:
    """Get ADD-6 data for a specific guideline."""
    return add6_data.get(guideline_id)
```

**Tasks:**
- [ ] Add `load_add6_data()` function to batch.py
- [ ] Include `add6_data` in each guideline entry
- [ ] Update `build_guideline_entry()` signature
- [ ] Update human-readable report format to show ADD-6

### 2.2 `record-decision` (record.py)

**Changes:**
1. Load ADD-6 data for the guideline
2. Require `--disagree-with-add6` flag if LLM's decision differs from ADD-6
3. When `--disagree-with-add6` is used, require `--notes` with justification
4. Store both classifications in the decision file

**New arguments:**
```python
parser.add_argument(
    "--disagree-with-add6",
    action="store_true",
    help="Acknowledge disagreement with MISRA ADD-6 classification (requires --notes justification)"
)
```

**Validation logic:**
```python
# Load ADD-6 data
add6 = load_add6_for_guideline(root, args.standard, args.guideline)

if add6:
    # Convert ADD-6 applicability to our format
    add6_app = add6.get(f"applicability_{context.replace('_', '_')}")  # "all_rust" or "safe_rust"
    add6_app_normalized = {"Yes": "yes", "No": "no", "Partial": "partial"}.get(add6_app)
    add6_cat = add6.get("adjusted_category")
    
    # Check for disagreement
    disagrees = (
        args.applicability != add6_app_normalized or
        args.adjusted_category != add6_cat
    )
    
    if disagrees and not args.disagree_with_add6:
        print(f"ERROR: Your decision disagrees with MISRA ADD-6 classification.")
        print(f"  ADD-6 applicability: {add6_app_normalized}, yours: {args.applicability}")
        print(f"  ADD-6 category: {add6_cat}, yours: {args.adjusted_category}")
        print(f"  Use --disagree-with-add6 with --notes explaining why.")
        sys.exit(1)
    
    if args.disagree_with_add6 and not args.notes:
        print("ERROR: --disagree-with-add6 requires --notes explaining the disagreement")
        sys.exit(1)
```

**Tasks:**
- [ ] Add `--disagree-with-add6` argument
- [ ] Implement ADD-6 loading and comparison
- [ ] Add disagreement validation logic
- [ ] Store `add6_agreement` in decision file
- [ ] Update decision file structure with ADD-6 reference

### 2.3 `merge-decisions` (merge.py)

**Changes:**
1. Report any disagreements found during merge
2. Aggregate disagreement counts in summary

**Tasks:**
- [ ] Add disagreement detection during merge
- [ ] Output summary of ADD-6 agreements/disagreements
- [ ] Include disagreements in applicability_changes for review

### 2.4 `apply-verification` (apply.py)

**Changes:**
1. Write dual classification to mapping file (both LLM and ADD-6)
2. Set `agrees_with_add6` field

**Tasks:**
- [ ] Update to write v3.0 mapping entries
- [ ] Preserve ADD-6 data in mapping file
- [ ] Update statistics with disagreement counts

### 2.5 New Tool: `show-add6`

**Purpose:** Quick lookup of ADD-6 data during verification.

**Usage:**
```bash
uv run show-add6 --guideline "Rule 22.8"
uv run show-add6 --guideline "Rule 22.8" --format json
uv run show-add6 --batch 3  # Show all ADD-6 data for batch
```

**Output (human):**
```
================================================================================
ADD-6 DATA: Rule 22.8
================================================================================

MISRA Category: Required
Decidability: Undecidable
Scope: System
Rationale: DC (Design Considerations)

Applicability:
  All Rust:  Yes
  Safe Rust: No

Adjusted Category: disapplied

Comment: only accessible through unsafe extern "C"

Search Guidance:
  - Rationale is DC (Design Considerations): Focus on design patterns, 
    architectural FLS content, and alternative Rust mechanisms
  - Safe Rust = No: Look for unsafe-specific FLS content
================================================================================
```

**Tasks:**
- [ ] Create `tools/src/fls_tools/standards/verification/show_add6.py`
- [ ] Add entry point to `pyproject.toml`
- [ ] Implement human-readable and JSON output modes
- [ ] Add search guidance based on rationale type

---

## Phase 3: AGENTS.md Updates

### 3.1 Phase 2 Workflow Updates

**Add to "Review extracted data" section:**

```markdown
1. **Check ADD-6 data first** (MISRA's official Rust classification):

   Before searching, review the ADD-6 data in the batch report:
   ```
   add6_data:
     rationale: ["UB", "DC"]
     applicability_all_rust: "Yes"
     applicability_safe_rust: "No"
     adjusted_category: "disapplied"
     comment: "only accessible through unsafe extern \"C\""
   ```

   Use this to inform your analysis:
   - **Rationale guides search strategy:**
     - `UB` → Search for "undefined behavior", safety-critical FLS content
     - `IDB` → Search for implementation-defined behavior, platform-specific FLS
     - `CQ` → Search for code quality, readability FLS content
     - `DC` → Search for design patterns, architectural FLS content
   
   - **Expected outcome:** Your decision should typically align with ADD-6.
     If you disagree, you'll need to use `--disagree-with-add6` with justification.
```

### 3.2 Decision Recording Updates

**Update `record-decision` examples:**

```markdown
**When agreeing with ADD-6 (typical case):**
```bash
uv run record-decision \
    --standard misra-c \
    --batch 4 \
    --guideline "Rule 22.8" \
    --context safe_rust \
    --decision accept_with_modifications \
    --applicability no \
    --adjusted-category disapplied \
    --rationale-type rust_prevents \
    --confidence high \
    --search-used "uuid:search-fls-deep:Rule 22.8:5" \
    ...
```

**When disagreeing with ADD-6 (requires justification):**
```bash
uv run record-decision \
    --standard misra-c \
    --batch 4 \
    --guideline "Rule 11.3" \
    --context all_rust \
    --decision accept_with_modifications \
    --applicability partial \          # ADD-6 says "Yes"
    --adjusted-category advisory \     # ADD-6 says "required"
    --rationale-type partial_mapping \
    --confidence high \
    --disagree-with-add6 \
    --notes "ADD-6 marks this as fully applicable, but FLS fls_xxx shows Rust's \
type system provides stronger guarantees than C. The rule only partially \
applies because transmute is the only escape hatch, not general pointer casts." \
    ...
```
```

### 3.3 Decision Summary Format Updates

**Add ADD-6 comparison column:**

```markdown
## Rule X.Y - <Title>

**ADD-6 Classification:**
- Rationale: UB, DC
- All Rust: Yes → required
- Safe Rust: No → disapplied
- Comment: "only accessible through unsafe extern \"C\""

**MISRA Concern:** <1-2 sentence summary>

**Rust Analysis:** <2-4 sentences>

| Context | ADD-6 App | ADD-6 Cat | Our App | Our Cat | Agrees? | Rationale Type | Key FLS |
|---------|-----------|-----------|---------|---------|---------|----------------|---------|
| all_rust | Yes | required | yes | required | ✓ | direct_mapping | fls_xxx |
| safe_rust | No | disapplied | no | disapplied | ✓ | rust_prevents | fls_yyy |
```

**Tasks:**
- [ ] Add ADD-6 data review to Phase 2 workflow
- [ ] Add rationale-based search guidance
- [ ] Update record-decision examples with --disagree-with-add6
- [ ] Update Decision Summary Format with ADD-6 comparison

---

## Phase 4: Validation & Testing

### 4.1 Update Validation Tools

**Tasks:**
- [ ] Update `validate-standards` to check v3.0 entries
- [ ] Add validation for ADD-6 agreement consistency
- [ ] Add disagreement count to validation output

### 4.2 Update Existing Schema Tests

**Tasks:**
- [ ] Ensure v1.0 and v2.0 entries still validate
- [ ] Test v3.0 entries with and without disagreements
- [ ] Test mixed-version mapping files

---

## Implementation Order

### Sprint 1: Schema Foundation
1. [ ] Update `batch_report.schema.json` to v3.0
2. [ ] Update `decision_file.schema.json` to v3.0
3. [ ] Update `fls_mapping.schema.json` with v3.0 entry type
4. [ ] Update shared constants for new enum values

### Sprint 2: Core Tool Updates
5. [ ] Update `verify-batch` to include ADD-6 data
6. [ ] Create `show-add6` tool
7. [ ] Update `record-decision` with --disagree-with-add6

### Sprint 3: Workflow Integration
8. [ ] Update `merge-decisions` with disagreement reporting
9. [ ] Update `apply-verification` for v3.0 output
10. [ ] Update AGENTS.md with new workflow guidance

### Sprint 4: Validation & Polish
11. [ ] Update validation tools
12. [ ] Test full workflow end-to-end
13. [ ] Update documentation

---

## Success Criteria

1. **Batch reports show ADD-6 data** for each guideline
2. **LLM decisions are validated** against ADD-6 classifications
3. **Disagreements require explicit flag** and justification
4. **Both classifications preserved** in final mapping file
5. **Disagreement summary** available at merge and apply time
6. **Search guidance** based on ADD-6 rationale type is documented

---

## Open Questions

1. **Migration strategy:** Should we migrate existing v2.0 entries to v3.0, or only new verifications?
   - Recommendation: Only new verifications use v3.0; existing v2.0 entries remain valid

2. **ADD-6 for other standards:** CERT C/C++ don't have ADD-6. How to handle?
   - Recommendation: ADD-6 fields are optional; tools skip ADD-6 validation for non-MISRA-C standards

3. **Partial disagreements:** What if only one of applicability/category differs?
   - Recommendation: Any difference triggers --disagree-with-add6 requirement

---

## Files to Modify

| File | Changes |
|------|---------|
| `coding-standards-fls-mapping/schema/batch_report.schema.json` | Add v3.0 with add6_data |
| `coding-standards-fls-mapping/schema/decision_file.schema.json` | Add v3.0 with add6_agreement |
| `coding-standards-fls-mapping/schema/fls_mapping.schema.json` | Add mapping_entry_v3 |
| `tools/src/fls_tools/standards/verification/batch.py` | Load and include ADD-6 data |
| `tools/src/fls_tools/standards/verification/record.py` | Add --disagree-with-add6 |
| `tools/src/fls_tools/standards/verification/merge.py` | Report disagreements |
| `tools/src/fls_tools/standards/verification/apply.py` | Write v3.0 entries |
| `tools/src/fls_tools/standards/verification/show_add6.py` | NEW: ADD-6 lookup tool |
| `tools/src/fls_tools/shared/constants.py` | Add ADD-6 related constants |
| `tools/pyproject.toml` | Add show-add6 entry point |
| `AGENTS.md` | Add ADD-6 workflow guidance |
