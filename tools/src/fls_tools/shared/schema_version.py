"""
Schema version detection and utilities for schema migrations.

This module provides utilities for detecting and working with schema versions
in mapping files, batch reports, decision files, and progress files.

Schema versions:
- v1.0: Flat structure with shared applicability fields
- v1.1: v1.0 + misra_add6 block (enriched via migration)
- v1.2: v1.1 + paragraph coverage fields (migrated with waiver if needed)
- v2.0: Per-context structure with independent all_rust and safe_rust sections
- v2.1: v2.0 + misra_add6 block (enriched via migration)
- v2.2: v2.1 + paragraph coverage fields per context (migrated with waiver if needed)
- v3.0: Per-context + misra_add6, fresh verification (structurally same as v2.1)
- v3.1: v3.0 + analysis_summary structured field (same per-context structure)
- v3.2: v3.1 + paragraph coverage fields per context (migrated with waiver if needed)
- v4.0: Per-context + misra_add6 + enforced paragraph coverage requirements

Version semantics:
- v1.1/v2.1 = Enriched legacy data (ADD-6 added via migration tool)
- v1.2/v2.2/v3.2 = Grandfather versions (paragraph fields added via migration, waiver for legacy)
- v3.x = Fresh verification decisions (created with full ADD-6 context)
- v4.0 = Fresh verification with enforced paragraph-level requirements

Note: is_v2_family() returns True for v2.x, v3.x, and v4.0 since they use per-context structure.
"""

from typing import Dict, Any, Literal, Optional

SchemaVersion = Literal["1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "3.0", "3.1", "3.2", "4.0"]


def detect_schema_version(data: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version from data.
    
    For guideline entries: looks for schema_version field
    For top-level files: looks for schema_version field
    
    Returns "1.0" if no version field is found (backwards compatibility).
    """
    return data.get("schema_version", "1.0")


def is_v1(data: Dict[str, Any]) -> bool:
    """Check if data is v1.0 format."""
    return detect_schema_version(data) == "1.0"


def is_v1_1(data: Dict[str, Any]) -> bool:
    """Check if data is v1.1 format (v1 + ADD-6)."""
    return detect_schema_version(data) == "1.1"


def is_v2(data: Dict[str, Any]) -> bool:
    """Check if data is v2.0 format."""
    return detect_schema_version(data) == "2.0"


def is_v2_1(data: Dict[str, Any]) -> bool:
    """Check if data is v2.1 format (v2 + ADD-6)."""
    return detect_schema_version(data) == "2.1"


def is_v3(data: Dict[str, Any]) -> bool:
    """Check if data is v3.x format (v3.0, v3.1, etc.)."""
    return str(detect_schema_version(data)).startswith("3.")


def is_v1_family(data: Dict[str, Any]) -> bool:
    """Check if data is v1 family (v1.0, v1.1, v1.2 - flat structure)."""
    return str(detect_schema_version(data)).startswith("1.")


def is_v2_family(data: Dict[str, Any]) -> bool:
    """Check if data is v2+ family (v2.x, v3.x, v4.x - per-context structure)."""
    version = str(detect_schema_version(data))
    # v2.x, v3.x, and v4.x use per-context structure
    return version.startswith("2.") or version.startswith("3.") or version.startswith("4.")


def has_add6_data(data: Dict[str, Any]) -> bool:
    """Check if entry has misra_add6 or misra_add6_snapshot block."""
    return "misra_add6" in data or "misra_add6_snapshot" in data


def is_enriched(data: Dict[str, Any]) -> bool:
    """Check if entry is an enriched version (v1.1 or v2.1)."""
    version = detect_schema_version(data)
    return version in ("1.1", "2.1")


def is_fresh_verification(data: Dict[str, Any]) -> bool:
    """Check if entry is from fresh verification (v3.0)."""
    return detect_schema_version(data) == "3.0"


def get_guideline_schema_version(guideline: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a guideline entry.
    
    v1.0 indicators: has applicability_all_rust, no misra_add6
    v1.1 indicators: has applicability_all_rust AND misra_add6
    v2.0 indicators: has all_rust, safe_rust nested objects, no misra_add6
    v2.1 indicators: has all_rust, safe_rust AND misra_add6
    v3.0 indicators: explicit schema_version "3.0" (structurally same as v2.1)
    """
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
    
    return "1.0"  # Default to v1


def get_decision_schema_version(decision: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a decision file.
    
    v1.0 indicators: has flat decision, confidence, fls_rationale_type fields, no misra_add6_snapshot
    v1.1 indicators: has flat structure AND misra_add6_snapshot
    v2.0 indicators: has all_rust, safe_rust nested objects, no misra_add6_snapshot
    v2.1 indicators: has all_rust, safe_rust AND misra_add6_snapshot
    v3.0 indicators: explicit schema_version "3.0" (structurally same as v2.1)
    """
    # Explicit version field takes precedence
    if decision.get("schema_version"):
        return decision["schema_version"]
    
    # Heuristic detection
    has_add6 = "misra_add6_snapshot" in decision
    has_per_context = "all_rust" in decision and "safe_rust" in decision
    has_flat = "decision" in decision and "fls_rationale_type" in decision
    
    if has_per_context:
        return "2.1" if has_add6 else "2.0"
    if has_flat:
        return "1.1" if has_add6 else "1.0"
    
    return "1.0"


def get_progress_schema_version(progress: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a progress file.
    
    v1.0 indicators: summary has total_verified, total_pending
    v2.0/v2.1/v3.0 indicators: summary has all_rust_verified, safe_rust_verified
    
    Note: Progress files don't distinguish v2.0/v2.1/v3.0 - they track verification
    state, not whether entries have ADD-6 data.
    """
    if progress.get("schema_version"):
        return progress["schema_version"]
    
    summary = progress.get("summary", {})
    if "all_rust_verified" in summary:
        return "2.0"
    if "total_verified" in summary:
        return "1.0"
    
    return "1.0"


def get_batch_report_schema_version(report: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a batch report.
    """
    return report.get("schema_version", "1.0")


# Applicability value mappings for v1 <-> v2 conversion

V1_TO_V2_APPLICABILITY = {
    "direct": "yes",
    "partial": "partial",
    "not_applicable": "no",
    "rust_prevents": "no",
    "unmapped": "no",
}

V2_TO_V1_APPLICABILITY = {
    "yes": "direct",
    "no": "not_applicable",
    "partial": "partial",
}


def convert_v1_applicability_to_v2(v1_value: str) -> str:
    """Convert v1 applicability value to v2 format."""
    return V1_TO_V2_APPLICABILITY.get(v1_value, "no")


def convert_v2_applicability_to_v1(v2_value: str) -> str:
    """Convert v2 applicability value to v1 format."""
    return V2_TO_V1_APPLICABILITY.get(v2_value, "not_applicable")


def normalize_rationale_type(rationale_type: Optional[str]) -> Optional[str]:
    """
    Normalize rationale type field names between v1 and v2.
    
    v1 uses: fls_rationale_type
    v2 uses: rationale_type
    
    Both use the same values: direct_mapping, partial_mapping, rust_alternative,
    rust_prevents, no_equivalent
    """
    return rationale_type  # Values are the same, just field name differs


# =============================================================================
# ADD-6 data block builders
# =============================================================================

def build_misra_add6_block(add6_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a misra_add6 block from ADD-6 source data.
    
    Args:
        add6_data: Raw ADD-6 data for a guideline from misra_rust_applicability.json
    
    Returns:
        Structured misra_add6 block for inclusion in mapping entries
    """
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


def build_misra_add6_snapshot(add6_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a misra_add6_snapshot block from ADD-6 source data.
    
    This is used in decision files to capture the ADD-6 state at decision time.
    Same structure as misra_add6 but without source_version.
    
    Args:
        add6_data: Raw ADD-6 data for a guideline from misra_rust_applicability.json
    
    Returns:
        Structured misra_add6_snapshot block for inclusion in decision files
    """
    return {
        "misra_category": add6_data.get("misra_category"),
        "decidability": add6_data.get("decidability"),
        "scope": add6_data.get("scope"),
        "rationale_codes": add6_data.get("rationale", []),
        "applicability_all_rust": add6_data.get("applicability_all_rust"),
        "applicability_safe_rust": add6_data.get("applicability_safe_rust"),
        "adjusted_category": add6_data.get("adjusted_category"),
        "comment": add6_data.get("comment"),
    }


# =============================================================================
# ADD-6 mismatch detection
# =============================================================================

def check_add6_mismatch(
    snapshot: Dict[str, Any],
    current: Dict[str, Any],
) -> list[str]:
    """
    Compare ADD-6 snapshot with current data, return list of differences.
    
    Used to detect if ADD-6 data changed between decision recording and apply.
    
    Args:
        snapshot: misra_add6_snapshot from decision file
        current: Current ADD-6 data from misra_rust_applicability.json
    
    Returns:
        List of difference descriptions (empty if no differences)
    """
    mismatches = []
    fields_to_check = [
        "misra_category",
        "decidability", 
        "scope",
        "applicability_all_rust",
        "applicability_safe_rust",
        "adjusted_category",
    ]
    
    for field in fields_to_check:
        snap_val = snapshot.get(field)
        curr_val = current.get(field)
        if snap_val != curr_val:
            mismatches.append(
                f"  {field}: \"{snap_val}\" (snapshot) vs \"{curr_val}\" (current)"
            )
    
    # Check rationale_codes (array comparison)
    snap_rationale = snapshot.get("rationale_codes", [])
    curr_rationale = current.get("rationale", [])
    if set(snap_rationale) != set(curr_rationale):
        mismatches.append(
            f"  rationale_codes: {snap_rationale} (snapshot) vs {curr_rationale} (current)"
        )
    
    return mismatches


# =============================================================================
# v4.0 and vX.2 version detection
# =============================================================================

def is_v1_2(data: Dict[str, Any]) -> bool:
    """Check if data is v1.2 format (v1.1 + paragraph fields, migrated with waiver)."""
    return detect_schema_version(data) == "1.2"


def is_v2_2(data: Dict[str, Any]) -> bool:
    """Check if data is v2.2 format (v2.1 + paragraph fields, migrated with waiver)."""
    return detect_schema_version(data) == "2.2"


def is_v3_2(data: Dict[str, Any]) -> bool:
    """Check if data is v3.2 format (v3.x + paragraph fields, migrated with waiver)."""
    return detect_schema_version(data) == "3.2"


def is_v4(data: Dict[str, Any]) -> bool:
    """Check if data is v4.0 format (enforced paragraph requirements)."""
    return detect_schema_version(data) == "4.0"


def is_grandfather_version(data: Dict[str, Any]) -> bool:
    """
    Check if data is a grandfather version (v1.2, v2.2, v3.2).
    
    Grandfather versions have paragraph fields added via migration, with migration
    waivers allowed for entries without paragraph-level matches.
    """
    version = detect_schema_version(data)
    return version in ("1.2", "2.2", "3.2")


def has_paragraph_coverage_fields(data: Dict[str, Any]) -> bool:
    """
    Check if entry has paragraph coverage fields.
    
    Returns True if the entry has paragraph_match_count field at the
    appropriate level (entry-level for v1, context-level for v2+).
    """
    version = detect_schema_version(data)
    
    # v1.x uses entry-level fields
    if version.startswith("1."):
        return "paragraph_match_count" in data
    
    # v2+/v3+/v4.0 uses per-context fields
    for ctx in ["all_rust", "safe_rust"]:
        ctx_data = data.get(ctx, {})
        if ctx_data and "paragraph_match_count" in ctx_data:
            return True
    
    return False


# =============================================================================
# Paragraph counting utilities
# =============================================================================

def count_matches_by_category(matches: list[Dict[str, Any]]) -> tuple[int, int]:
    """
    Count paragraph-level and section-level matches.
    
    Args:
        matches: List of FLS match objects with 'category' field
    
    Returns:
        Tuple of (paragraph_count, section_count)
        - paragraph_count: matches where category != 0
        - section_count: matches where category == 0
    """
    paragraph_count = 0
    section_count = 0
    
    for match in matches:
        category = match.get("category", 0)
        if category == 0:
            section_count += 1
        else:
            paragraph_count += 1
    
    return paragraph_count, section_count


def count_entry_matches(entry: Dict[str, Any]) -> tuple[int, int]:
    """
    Count paragraph and section matches for an entry.
    
    Handles both v1 (flat) and v2+ (per-context) structures.
    For v2+, returns the sum across both contexts.
    
    Args:
        entry: A mapping entry or decision file
    
    Returns:
        Tuple of (paragraph_count, section_count)
    """
    version = detect_schema_version(entry)
    
    # v1.x uses flat structure
    if version.startswith("1."):
        matches = entry.get("accepted_matches", [])
        return count_matches_by_category(matches)
    
    # v2+/v3+/v4.0 uses per-context structure
    total_para = 0
    total_section = 0
    
    for ctx in ["all_rust", "safe_rust"]:
        ctx_data = entry.get(ctx, {})
        if ctx_data:
            matches = ctx_data.get("accepted_matches", [])
            para, section = count_matches_by_category(matches)
            total_para += para
            total_section += section
    
    return total_para, total_section


def count_context_matches(ctx_data: Dict[str, Any]) -> tuple[int, int]:
    """
    Count paragraph and section matches for a single context.
    
    Args:
        ctx_data: Context data (all_rust or safe_rust) from an entry
    
    Returns:
        Tuple of (paragraph_count, section_count)
    """
    matches = ctx_data.get("accepted_matches", [])
    return count_matches_by_category(matches)


# =============================================================================
# Paragraph coverage validation
# =============================================================================

MIGRATION_WAIVER_PREFIX = "Migrated from"
MIN_WAIVER_LENGTH = 50


def is_migration_waiver(waiver: Optional[str]) -> bool:
    """Check if a waiver is a migration waiver (starts with 'Migrated from')."""
    if waiver is None:
        return False
    return waiver.startswith(MIGRATION_WAIVER_PREFIX)


def validate_paragraph_coverage_v1(
    entry: Dict[str, Any],
    strict: bool = False,
) -> list[str]:
    """
    Validate paragraph coverage for a v1.x entry.
    
    Args:
        entry: A v1.x mapping entry
        strict: If True, enforce 50-char minimum for non-migration waivers
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    version = detect_schema_version(entry)
    
    if not version.startswith("1."):
        return ["Not a v1.x entry"]
    
    matches = entry.get("accepted_matches", [])
    para_count, section_count = count_matches_by_category(matches)
    waiver = entry.get("paragraph_level_waiver")
    
    # Check actual counts match stored counts (if present)
    stored_para = entry.get("paragraph_match_count")
    stored_section = entry.get("section_match_count")
    
    if stored_para is not None and stored_para != para_count:
        errors.append(
            f"paragraph_match_count mismatch: stored={stored_para}, actual={para_count}"
        )
    if stored_section is not None and stored_section != section_count:
        errors.append(
            f"section_match_count mismatch: stored={stored_section}, actual={section_count}"
        )
    
    # v1.2 and v4.0 require paragraph coverage
    if version in ("1.2", "4.0"):
        if para_count == 0 and not waiver:
            errors.append(
                f"No paragraph-level matches (has {section_count} section matches). "
                "Requires paragraph_level_waiver with justification."
            )
        elif waiver and strict and not is_migration_waiver(waiver):
            if len(waiver) < MIN_WAIVER_LENGTH:
                errors.append(
                    f"paragraph_level_waiver too short ({len(waiver)} chars, min {MIN_WAIVER_LENGTH})"
                )
    
    return errors


def validate_paragraph_coverage_context(
    ctx_name: str,
    ctx_data: Dict[str, Any],
    schema_version: str,
    strict: bool = False,
) -> list[str]:
    """
    Validate paragraph coverage for a single context.
    
    Args:
        ctx_name: Context name ('all_rust' or 'safe_rust')
        ctx_data: Context data from an entry
        schema_version: The entry's schema version
        strict: If True, enforce 50-char minimum for non-migration waivers
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not ctx_data:
        return errors  # Empty/null context is allowed (scaffolded)
    
    # Check if context is scaffolded (decision is null)
    if ctx_data.get("decision") is None:
        return errors  # Scaffolded context, no validation needed
    
    matches = ctx_data.get("accepted_matches", [])
    para_count, section_count = count_matches_by_category(matches)
    waiver = ctx_data.get("paragraph_level_waiver")
    
    # Check actual counts match stored counts (if present)
    stored_para = ctx_data.get("paragraph_match_count")
    stored_section = ctx_data.get("section_match_count")
    
    if stored_para is not None and stored_para != para_count:
        errors.append(
            f"{ctx_name}: paragraph_match_count mismatch: stored={stored_para}, actual={para_count}"
        )
    if stored_section is not None and stored_section != section_count:
        errors.append(
            f"{ctx_name}: section_match_count mismatch: stored={stored_section}, actual={section_count}"
        )
    
    # v2.2, v3.2, and v4.0 require paragraph coverage
    if schema_version in ("2.2", "3.2", "4.0"):
        if para_count == 0 and not waiver:
            errors.append(
                f"{ctx_name}: No paragraph-level matches (has {section_count} section matches). "
                "Requires paragraph_level_waiver with justification."
            )
        elif waiver and strict and not is_migration_waiver(waiver):
            if len(waiver) < MIN_WAIVER_LENGTH:
                errors.append(
                    f"{ctx_name}: paragraph_level_waiver too short ({len(waiver)} chars, min {MIN_WAIVER_LENGTH})"
                )
    
    return errors


def validate_paragraph_coverage(
    entry: Dict[str, Any],
    strict: bool = False,
) -> list[str]:
    """
    Validate paragraph coverage for a mapping entry.
    
    Handles both v1.x (flat) and v2+/v3+/v4.0 (per-context) structures.
    
    Args:
        entry: A mapping entry
        strict: If True, enforce 50-char minimum for non-migration waivers
    
    Returns:
        List of validation errors (empty if valid)
    """
    version = detect_schema_version(entry)
    
    # v1.x uses flat structure
    if version.startswith("1."):
        return validate_paragraph_coverage_v1(entry, strict)
    
    # v2+/v3+/v4.0 uses per-context structure
    errors = []
    
    for ctx_name in ["all_rust", "safe_rust"]:
        ctx_data = entry.get(ctx_name, {})
        ctx_errors = validate_paragraph_coverage_context(
            ctx_name, ctx_data, version, strict
        )
        errors.extend(ctx_errors)
    
    return errors


def build_migration_waiver(
    from_version: str,
    date: str,
    paragraph_count: int,
    section_count: int,
) -> str:
    """
    Build a migration waiver string.
    
    Args:
        from_version: Original schema version (e.g., "2.1")
        date: Migration date in YYYY-MM-DD format
        paragraph_count: Number of paragraph-level matches
        section_count: Number of section-level matches
    
    Returns:
        Migration waiver string
    """
    if paragraph_count == 0 and section_count == 0:
        status = "requires re-verification"
    elif paragraph_count == 0:
        status = "requires re-verification for paragraph coverage"
    else:
        status = "OK"
    
    return (
        f"Migrated from v{from_version} on {date} - "
        f"has {paragraph_count} paragraph matches, {section_count} section matches - "
        f"{status}"
    )
