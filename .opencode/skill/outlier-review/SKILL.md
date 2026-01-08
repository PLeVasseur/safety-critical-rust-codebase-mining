---
name: outlier-review
description: Handle INVESTIGATION_REQUEST markers during MISRA-to-FLS outlier review - read FLS content, analyze relevance, and record findings
---

## Purpose

This skill handles `INVESTIGATION_REQUEST:` markers output by the `review-outliers` tool during interactive review of MISRA-to-FLS mapping outliers. When you see this marker, you should:

1. Parse the JSON request
2. Read relevant source files
3. Consider user guidance if provided
4. Record findings using the `record-investigation` tool
5. Report findings to the user
6. Instruct user to press Enter to continue

## Recognizing Investigation Requests

Watch for this pattern in bash tool output:

```
INVESTIGATION_REQUEST:{"guideline_id":"Dir 4.3","aspect":"fls_removal","fls_id":"fls_3fg60jblx0xb","context":"all_rust","user_guidance":"..."}

Investigation requested. Perform investigation and press Enter when complete...
```

When you see this, immediately begin the investigation workflow below.

## Investigation Workflow

### Step 1: Parse the Request

Extract these fields from the JSON:
- `guideline_id` - The MISRA guideline (e.g., "Dir 4.3", "Rule 10.1")
- `aspect` - What to investigate: `fls_removal`, `fls_addition`, `categorization`, `specificity`, `add6_divergence`, or `all`
- `fls_id` - (optional) Specific FLS paragraph ID
- `context` - (optional) `all_rust` or `safe_rust`
- `user_guidance` - (optional) Natural language guidance from the user

### Step 2: Gather Context

Read these files based on the aspect:

**For FLS-related aspects (fls_removal, fls_addition, specificity):**
1. Find which FLS chapter contains the FLS ID:
   - Check `tools/data/fls_section_mapping.json` for section info
   - Read `embeddings/fls/chapter_XX.json` for full content
2. Look for the specific paragraph in the chapter's `sections[].rubrics` structure

**For all aspects:**
1. Read the outlier file: `cache/analysis/outlier_analysis/{guideline}.json`
   - Replace spaces with underscores, dots with dots (e.g., "Dir 4.3" -> "Dir_4.3.json")
2. Check `cache/misra_c_extracted_text.json` for MISRA rationale (if exists)
3. Check `coding-standards-fls-mapping/misra_rust_applicability.json` for ADD-6 data

### Step 3: Consider User Guidance

If `user_guidance` is provided, it contains domain knowledge or specific questions from the user. Factor this into your analysis. For example:
- "MISRA Dir 4.3 is about encapsulation, not safety" - Focus on whether the FLS shows encapsulation
- "ADD-6 says Yes but asm! requires unsafe" - Verify the divergence is real

### Step 4: Formulate Findings

Analyze and determine:
- **FLS Content Summary**: What does the FLS actually say?
- **Relevance Assessment**: How does this relate to the MISRA concern?
- **Recommendation**: KEEP, REMOVE, ACCEPT, or REJECT (with brief reason)
- **Confidence**: high, medium, or low

### Step 5: Record Findings

Use the `record-investigation` tool:

```bash
cd tools && uv run record-investigation \
    --standard misra-c \
    --guideline "Dir 4.3" \
    --aspect fls_removal \
    --fls-id fls_3fg60jblx0xb \
    --context all_rust \
    --source "embeddings/fls/chapter_22.json" \
    --source "cache/misra_c_extracted_text.json" \
    --fls-content "Brief summary of what FLS says" \
    --relevance "How this relates to MISRA concern" \
    --recommendation "KEEP" \
    --confidence high \
    --user-guidance "User's guidance if provided"
```

**Required parameters:**
- `--standard`: Always `misra-c` for now
- `--guideline`: From the request
- `--aspect`: From the request
- `--relevance`: Your assessment
- `--recommendation`: Your recommendation
- `--confidence`: high/medium/low

**Optional parameters:**
- `--fls-id`: If investigating specific FLS ID
- `--context`: If context-specific
- `--source`: Files you consulted (repeat for multiple)
- `--fls-content`: Summary of FLS content
- `--user-guidance`: Echo back user's guidance
- `--notes`: Additional observations

### Step 6: Report to User

After recording, tell the user:
1. What you found
2. Your recommendation
3. That they should press Enter to continue the review tool

Example response:
> "Investigation complete for fls_3fg60jblx0xb (Dir 4.3):
> 
> **FLS Content**: The FLS states that inline assembly must be wrapped in the asm! macro invocation.
> 
> **Relevance**: This directly addresses MISRA Dir 4.3's requirement for assembly encapsulation - the asm! macro provides syntactic encapsulation.
> 
> **Recommendation**: KEEP (high confidence) - This paragraph provides citable normative text.
> 
> Press Enter in the review tool to continue."

## Key File Locations

| File | Purpose |
|------|---------|
| `cache/analysis/outlier_analysis/*.json` | Outlier files with LLM analysis |
| `embeddings/fls/chapter_*.json` | FLS content with paragraph-level detail |
| `tools/data/fls_section_mapping.json` | FLS section hierarchy |
| `cache/misra_c_extracted_text.json` | Full MISRA rationale text |
| `coding-standards-fls-mapping/misra_rust_applicability.json` | ADD-6 data |
| `coding-standards-fls-mapping/mappings/misra_c_to_fls.json` | Current mappings |

## FLS Chapter Structure

FLS chapters are in `embeddings/fls/chapter_XX.json` with this structure:

```json
{
  "chapter": 22,
  "title": "Inline Assembly",
  "sections": [
    {
      "fls_id": "fls_z1il3w9nulzy",
      "title": "Inline Assembly",
      "category": 0,
      "content": "...",
      "rubrics": {
        "-2": {
          "paragraphs": {
            "fls_3fg60jblx0xb": "Inline assembly is written as...",
            "fls_4lb6yh12w1cv": "Invoking macro core::arch::asm..."
          }
        }
      }
    }
  ]
}
```

Category codes:
- `0` = Section header
- `-2` = Legality Rules (compiler-enforced)
- `-3` = Dynamic Semantics (runtime behavior)
- `-4` = Undefined Behavior
- `-5` = Implementation Requirements

## Example Investigation

**Request:**
```
INVESTIGATION_REQUEST:{"guideline_id":"Dir 4.3","aspect":"fls_removal","fls_id":"fls_3fg60jblx0xb","context":"all_rust","user_guidance":"MISRA Dir 4.3 is about encapsulation of assembly. Does asm! macro provide encapsulation?"}
```

**Actions:**
1. Read `embeddings/fls/chapter_22.json` to find fls_3fg60jblx0xb
2. Found: "Inline assembly is written as an assembly code block that is wrapped inside a macro invocation"
3. This shows encapsulation - assembly MUST go through asm! macro
4. Record:
   ```bash
   cd tools && uv run record-investigation \
       --standard misra-c --guideline "Dir 4.3" \
       --aspect fls_removal --fls-id fls_3fg60jblx0xb --context all_rust \
       --source "embeddings/fls/chapter_22.json" \
       --fls-content "Assembly must be wrapped in asm! macro invocation" \
       --relevance "Directly satisfies encapsulation requirement - assembly is syntactically encapsulated in macro" \
       --recommendation "KEEP" --confidence high \
       --user-guidance "User asked about encapsulation - asm! provides syntactic encapsulation"
   ```
5. Report findings to user
