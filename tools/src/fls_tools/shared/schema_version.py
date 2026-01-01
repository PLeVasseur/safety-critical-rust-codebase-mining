"""
Schema version detection and utilities for v1/v2 migration.

This module provides utilities for detecting and working with schema versions
in mapping files, batch reports, decision files, and progress files.

Schema versions:
- v1.0: Flat structure with shared applicability fields
- v2.0: Per-context structure with independent all_rust and safe_rust sections
"""

from typing import Dict, Any, Literal, Optional

SchemaVersion = Literal["1.0", "2.0"]


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


def is_v2(data: Dict[str, Any]) -> bool:
    """Check if data is v2.0 format."""
    return detect_schema_version(data) == "2.0"


def get_guideline_schema_version(guideline: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a guideline entry.
    
    v1.0 indicators: has applicability_all_rust, applicability_safe_rust fields
    v2.0 indicators: has all_rust, safe_rust nested objects
    """
    if guideline.get("schema_version"):
        return guideline["schema_version"]
    
    # Heuristic detection for unversioned entries
    if "all_rust" in guideline and "safe_rust" in guideline:
        return "2.0"
    if "applicability_all_rust" in guideline:
        return "1.0"
    
    return "1.0"  # Default to v1


def get_decision_schema_version(decision: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a decision file.
    
    v1.0 indicators: has flat decision, confidence, fls_rationale_type fields
    v2.0 indicators: has all_rust, safe_rust nested objects
    """
    if decision.get("schema_version"):
        return decision["schema_version"]
    
    # Heuristic detection
    if "all_rust" in decision and "safe_rust" in decision:
        return "2.0"
    if "decision" in decision and "fls_rationale_type" in decision:
        return "1.0"
    
    return "1.0"


def get_progress_schema_version(progress: Dict[str, Any]) -> SchemaVersion:
    """
    Detect schema version for a progress file.
    
    v1.0 indicators: summary has total_verified, total_pending
    v2.0 indicators: summary has all_rust_verified, safe_rust_verified
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
