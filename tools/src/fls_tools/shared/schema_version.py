"""
Schema version detection and utilities for schema migrations.

This module provides utilities for detecting and working with schema versions
in mapping files, batch reports, decision files, and progress files.

Schema versions:
- v1.0: Flat structure with shared applicability fields
- v1.1: v1.0 + misra_add6 block (enriched via migration)
- v2.0: Per-context structure with independent all_rust and safe_rust sections
- v2.1: v2.0 + misra_add6 block (enriched via migration)
- v3.0: Per-context + misra_add6, fresh verification (structurally same as v2.1)

Version semantics:
- v1.1/v2.1 = Enriched legacy data (ADD-6 added via migration tool)
- v3.0 = Fresh verification decisions (created with full ADD-6 context)
"""

from typing import Dict, Any, Literal, Optional

SchemaVersion = Literal["1.0", "1.1", "2.0", "2.1", "3.0"]


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
    """Check if data is v3.0 format."""
    return detect_schema_version(data) == "3.0"


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
