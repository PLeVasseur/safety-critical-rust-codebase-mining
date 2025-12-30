# Coding Standards to FLS Mapping

This directory contains mappings from safety-critical coding standards (MISRA C, MISRA C++, CERT C, CERT C++) to the Ferrocene Language Specification (FLS) for Rust.

## Purpose

The Safety-Critical Rust Consortium needs to understand how existing C/C++ safety coding standards relate to Rust language constructs. This mapping enables:

1. **Prioritization**: Identify which FLS sections are most frequently referenced by safety standards
2. **Gap Analysis**: Find areas where Rust's design prevents C/C++ issues entirely
3. **Documentation**: Provide traceability from established standards to Rust equivalents
4. **Tool Development**: Support static analysis tools that need to map C/C++ rules to Rust

## Directory Structure

```
coding-standards-fls-mapping/
├── schema/
│   ├── coding_standard_rules.schema.json   # Schema for rule/directive listings
│   └── fls_mapping.schema.json             # Schema for FLS mappings
├── standards/                               # Extracted rule listings
│   ├── misra_c_2025.json                   # MISRA C:2025 rules & directives
│   ├── misra_cpp_2023.json                 # MISRA C++:2023 rules & directives
│   ├── cert_c.json                         # CERT C rules & recommendations
│   └── cert_cpp.json                       # CERT C++ rules
├── mappings/                                # FLS mappings (deliverables)
│   ├── misra_c_to_fls.json                 # MISRA C → FLS IDs
│   ├── misra_cpp_to_fls.json               # MISRA C++ → FLS IDs
│   ├── cert_c_to_fls.json                  # CERT C → FLS IDs
│   └── cert_cpp_to_fls.json                # CERT C++ → FLS IDs
└── README.md
```

## Standards Summary

| Standard | Version | Rules | Directives | Recommendations | Total |
|----------|---------|-------|------------|-----------------|-------|
| MISRA C | 2025 | 190 | 22 | - | 212 |
| MISRA C++ | 2023 | 168 | 4 | - | 172 |
| CERT C | 2016 Edition | 123 | - | 183 | 306 |
| CERT C++ | 2016 Edition | 143 | - | 0* | 143 |

*CERT C++ recommendations were removed from the wiki pending review.

## Guideline Types

### MISRA Terminology
- **Rule**: Normative requirement that code must follow
- **Directive**: Higher-level guidance that may require judgment to apply

### CERT Terminology
- **Rule**: Normative requirement (violations are security issues)
- **Recommendation**: Best practice guidance (violations reduce quality)

## Mapping Applicability Values

Each guideline is mapped with an `applicability` field:

| Value | Meaning | Example |
|-------|---------|---------|
| `direct` | Guideline maps directly to FLS concept(s) | Memory allocation rules → FLS ownership |
| `partial` | Concept exists but Rust handles it differently | Integer overflow (Rust has checked arithmetic in debug) |
| `not_applicable` | C/C++ specific with no Rust equivalent | Preprocessor rules (Rust has no preprocessor) |
| `rust_prevents` | Rust's design prevents the issue entirely | Use-after-free (prevented by borrow checker) |
| `unmapped` | Awaiting expert mapping | Initial state for all guidelines |

## Usage

### Validation

Validate all JSON files against their schemas:

```bash
cd tools
uv run python validate_coding_standards.py
```

Check that all guidelines have mapping entries:

```bash
uv run python validate_coding_standards.py --check-coverage
```

### Regenerating Standards Files

**MISRA** (requires PDFs in `cache/misra-standards/`):

```bash
uv run python extract_misra_rules.py
```

**CERT** (scrapes from SEI wiki):

```bash
uv run python scrape_cert_rules.py
```

### Cross-Reference Analysis

Once mappings are populated, analyze FLS coverage frequency:

```bash
uv run python analyze_fls_coverage.py
```

## Mapping Workflow

1. **Select a guideline** from one of the mapping files (start with `applicability: "unmapped"`)

2. **Read the guideline** in its original standard:
   - MISRA: See PDF in `cache/misra-standards/`
   - CERT C: https://wiki.sei.cmu.edu/confluence/display/c/
   - CERT C++: https://wiki.sei.cmu.edu/confluence/display/cplusplus/

3. **Identify relevant FLS sections** by consulting:
   - `tools/fls_section_mapping.json` - canonical FLS section list with IDs
   - https://rust-lang.github.io/fls/ - FLS documentation

4. **Update the mapping** in the appropriate `mappings/*.json` file:
   ```json
   {
     "guideline_id": "MEM30-C",
     "guideline_type": "rule",
     "fls_ids": ["fls_svkx6szhr472", "fls_u2mzjgiwng0"],
     "fls_sections": ["15.1", "15.2"],
     "applicability": "rust_prevents",
     "confidence": "high",
     "notes": "Rust's ownership system prevents use-after-free at compile time"
   }
   ```

5. **Validate** after updates:
   ```bash
   uv run python validate_coding_standards.py
   ```

## Schema Details

### coding_standard_rules.schema.json

Defines the structure for listing rules/directives/recommendations:

```json
{
  "standard": "MISRA-C",
  "version": "2025",
  "categories": [
    {
      "id": "MEM",
      "name": "Memory Management",
      "guidelines": [
        {
          "id": "Rule 21.3",
          "title": "The memory allocation...",
          "guideline_type": "rule"
        }
      ]
    }
  ]
}
```

### fls_mapping.schema.json

Defines the structure for FLS mappings:

```json
{
  "standard": "MISRA-C",
  "standard_version": "2025",
  "fls_version": "1.0 (2024)",
  "mappings": [
    {
      "guideline_id": "Rule 21.3",
      "guideline_type": "rule",
      "fls_ids": ["fls_abc123"],
      "fls_sections": ["15.1"],
      "applicability": "partial",
      "confidence": "medium",
      "notes": "..."
    }
  ]
}
```

## Data Sources

- **MISRA C:2025**: Extracted from official PDF (not redistributed)
- **MISRA C++:2023**: Extracted from official PDF (not redistributed)
- **CERT C**: Scraped from https://wiki.sei.cmu.edu/confluence/display/c/
- **CERT C++**: Scraped from https://wiki.sei.cmu.edu/confluence/display/cplusplus/
- **FLS**: https://rust-lang.github.io/fls/

## Contributing

When adding or updating mappings:

1. Use the validation script to ensure schema compliance
2. Include meaningful `notes` explaining the mapping rationale
3. Set appropriate `confidence` level based on certainty
4. Update the `mapping_date` in the file header

## License

The mapping data in this repository is provided for safety analysis purposes.

- MISRA standards are copyright MISRA Ltd. Only rule numbers and titles are extracted.
- CERT standards are available under SEI terms. Only rule numbers and titles are used.
- FLS is available under Apache 2.0 / MIT license.
