"""
Shared utilities for analysis tools.

This module provides:
- Path helpers for analysis directories
- Data loading for comparison data, outlier analysis, review state
- Flag computation for identifying outliers
- Batch pattern helpers
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fls_tools.shared import (
    get_cache_dir,
    get_project_root,
    get_verification_progress_path,
    get_standard_mappings_path,
    get_misra_rust_applicability_path,
    get_standard_extracted_text_path,
    get_batch_decisions_dir,
    get_fls_chapter_path,
    get_fls_dir,
    normalize_standard,
    is_v2_family,
    is_v1_family,
    load_fls_chapters,
    build_fls_metadata,
)


# =============================================================================
# Constants
# =============================================================================

FLAG_TYPES = [
    "applicability_differs_from_add6",
    "adjusted_category_differs_from_add6",
    "fls_removed",
    "fls_added",
    "specificity_decreased",
    "rationale_type_changed",
    "batch_pattern_outlier",
    "missing_analysis_summary",
    "missing_search_tools",
    "multi_dimension_outlier",
]

OUTLIER_THRESHOLDS = {
    "fls_removed": 1,  # Any removal is flagged
    "fls_added": 1,  # Any addition is flagged (requires justification)
    "systematic_pattern": 2,  # 2+ occurrences = systematic
    "multi_dimension": 2,  # 2+ flags = multi-dimension outlier
}

# Batch expected patterns (from progress.json batch definitions)
BATCH_EXPECTED_PATTERNS = {
    1: {
        "name": "High-score direct mappings",
        "all_rust": {"applicability": "yes", "rationale_type": "direct_mapping"},
        "safe_rust": {"applicability": "yes", "rationale_type": "direct_mapping"},
    },
    2: {
        "name": "Not applicable",
        "all_rust": {"applicability": "no", "rationale_type": "no_equivalent"},
        "safe_rust": {"applicability": "no", "rationale_type": "no_equivalent"},
    },
    3: {
        "name": "Stdlib & Resources",
        "all_rust": {"applicability": "yes"},  # rationale_type varies
        "safe_rust": {"applicability": "no"},  # often not applicable in safe Rust
    },
    4: {
        "name": "Medium-score direct",
        "all_rust": {"applicability": "yes", "rationale_type": "direct_mapping"},
        "safe_rust": {},  # varies
    },
    5: {
        "name": "Edge cases",
        "all_rust": {},  # varies (partial, rust_prevents, etc.)
        "safe_rust": {},
    },
}


# =============================================================================
# Path Helpers
# =============================================================================

def get_analysis_dir(root: Path | None = None) -> Path:
    """Get the analysis output directory: cache/analysis/"""
    root = root or get_project_root()
    return get_cache_dir(root) / "analysis"


def get_comparison_data_dir(root: Path | None = None) -> Path:
    """Get the comparison data directory: cache/analysis/comparison_data/"""
    return get_analysis_dir(root) / "comparison_data"


def get_outlier_analysis_dir(root: Path | None = None) -> Path:
    """Get the outlier analysis directory: cache/analysis/outlier_analysis/"""
    return get_analysis_dir(root) / "outlier_analysis"


def get_reports_dir(root: Path | None = None) -> Path:
    """Get the reports directory: cache/analysis/reports/"""
    return get_analysis_dir(root) / "reports"


def get_review_state_path(root: Path | None = None) -> Path:
    """Get the review state file path: cache/analysis/review_state.json"""
    return get_analysis_dir(root) / "review_state.json"


def guideline_to_filename(guideline_id: str) -> str:
    """Convert guideline ID to safe filename (e.g., 'Rule 10.1' -> 'Rule_10.1').
    
    Note: Preserves dots since existing decision files use format 'Rule_10.1.json'.
    """
    return guideline_id.replace(" ", "_")


def filename_to_guideline(filename: str) -> str:
    """Convert filename back to guideline ID (e.g., 'Rule_10.1' -> 'Rule 10.1')"""
    # Remove .json extension if present
    name = filename.replace(".json", "")
    # Replace first underscore with space: "Rule_10.1" -> "Rule 10.1"
    parts = name.split("_", 1)
    if len(parts) == 2 and parts[0] in ("Rule", "Dir"):
        return f"{parts[0]} {parts[1]}"
    return name.replace("_", " ")


# =============================================================================
# Data Loading
# =============================================================================

def load_json_file(path: Path) -> dict | None:
    """Load a JSON file, return None if not found."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_json_file(path: Path, data: dict, indent: int = 2) -> None:
    """Save data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent)


def load_comparison_data(guideline_id: str, batch: int, root: Path | None = None) -> dict | None:
    """Load comparison data for a specific guideline."""
    comp_dir = get_comparison_data_dir(root) / f"batch{batch}"
    filename = guideline_to_filename(guideline_id) + ".json"
    return load_json_file(comp_dir / filename)


def load_outlier_analysis(guideline_id: str, root: Path | None = None) -> dict | None:
    """Load outlier analysis for a specific guideline."""
    outlier_dir = get_outlier_analysis_dir(root)
    filename = guideline_to_filename(guideline_id) + ".json"
    return load_json_file(outlier_dir / filename)


def save_outlier_analysis(guideline_id: str, data: dict, root: Path | None = None) -> Path:
    """Save outlier analysis for a specific guideline."""
    outlier_dir = get_outlier_analysis_dir(root)
    filename = guideline_to_filename(guideline_id) + ".json"
    path = outlier_dir / filename
    save_json_file(path, data)
    return path


def load_review_state(root: Path | None = None) -> dict:
    """Load review state, returning default structure if not found."""
    path = get_review_state_path(root)
    state = load_json_file(path)
    if state is None:
        state = {
            "last_updated": None,
            "bulk_rules": {
                "accept_removals": [],
                "accept_additions": [],
                "notes": None,
            },
            "summary": {
                "total_outliers": 0,
                "fully_reviewed": 0,
                "partially_reviewed": 0,
                "pending": 0,
                "by_aspect": {
                    "categorization": {"accepted": 0, "rejected": 0, "pending": 0},
                    "fls_removals": {"accepted": 0, "rejected": 0, "pending": 0},
                    "fls_additions": {"accepted": 0, "rejected": 0, "pending": 0},
                    "add6_divergence": {"accepted": 0, "rejected": 0, "pending": 0},
                },
            },
        }
    return state


def save_review_state(state: dict, root: Path | None = None) -> None:
    """Save review state."""
    state["last_updated"] = datetime.utcnow().isoformat() + "Z"
    path = get_review_state_path(root)
    save_json_file(path, state)


def load_mapping_file(standard: str, root: Path | None = None) -> dict:
    """Load the mapping file as a dict keyed by guideline_id."""
    standard = normalize_standard(standard)
    path = get_standard_mappings_path(root=root, standard=standard)
    data = load_json_file(path)
    if data is None:
        return {}
    # Convert list to dict keyed by guideline_id
    # Support both "mappings" (current format) and "guidelines" (legacy) keys
    mappings_list = data.get("mappings", []) or data.get("guidelines", [])
    return {g["guideline_id"]: g for g in mappings_list}


def load_add6_data(root: Path | None = None) -> dict:
    """Load MISRA ADD-6 Rust applicability data as dict keyed by guideline ID."""
    path = get_misra_rust_applicability_path(root)
    data = load_json_file(path)
    if data is None:
        return {}
    # ADD-6 data has "guidelines" key containing the mapping
    return data.get("guidelines", {})


def load_misra_extracted_text(standard: str, root: Path | None = None) -> dict:
    """Load MISRA extracted text (rationale, amplification)."""
    standard = normalize_standard(standard)
    path = get_standard_extracted_text_path(root=root, standard=standard)
    return load_json_file(path) or {}


def load_progress_file(standard: str, root: Path | None = None) -> dict:
    """Load verification progress file."""
    standard = normalize_standard(standard)
    path = get_verification_progress_path(root=root, standard=standard)
    return load_json_file(path) or {}


def load_decision_file(
    standard: str, batch: int, guideline_id: str, root: Path | None = None
) -> dict | None:
    """Load a decision file for a specific guideline."""
    standard = normalize_standard(standard)
    decisions_dir = get_batch_decisions_dir(root=root, standard=standard, batch=batch)
    filename = guideline_to_filename(guideline_id) + ".json"
    return load_json_file(decisions_dir / filename)


def load_all_decision_files(
    standard: str, batch: int, root: Path | None = None
) -> dict[str, dict]:
    """Load all decision files for a batch, keyed by guideline_id."""
    standard = normalize_standard(standard)
    decisions_dir = get_batch_decisions_dir(root=root, standard=standard, batch=batch)
    decisions = {}
    if decisions_dir.exists():
        for f in decisions_dir.glob("*.json"):
            data = load_json_file(f)
            if data and "guideline_id" in data:
                decisions[data["guideline_id"]] = data
    return decisions


# =============================================================================
# FLS Content Loading
# =============================================================================

# Cache for FLS metadata (expensive to rebuild)
_fls_metadata_cache: tuple[dict, dict] | None = None


def get_fls_metadata(root: Path | None = None) -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Get cached FLS metadata (sections and paragraphs).
    
    Returns:
        Tuple of (sections_metadata, paragraphs_metadata)
        - sections_metadata: fls_id -> {title, chapter, category}
        - paragraphs_metadata: para_id -> {text, section_fls_id, section_title, category, category_name, chapter}
    """
    global _fls_metadata_cache
    if _fls_metadata_cache is None:
        chapters = load_fls_chapters(root)
        _fls_metadata_cache = build_fls_metadata(chapters)
    return _fls_metadata_cache


def load_fls_content(fls_id: str, root: Path | None = None) -> dict | None:
    """
    Load FLS content by ID (handles both section-level and paragraph-level IDs).
    
    For section-level IDs:
        Returns dict with:
        - fls_id: The section FLS ID
        - title: Section title
        - content: Section text (intro/overview)
        - chapter: Chapter number
        - category: Category code (0 for sections)
        - rubrics: Dict of rubric category -> list of paragraph texts
        - is_paragraph: False
    
    For paragraph-level IDs:
        Returns dict with:
        - fls_id: The paragraph FLS ID
        - title: Parent section title
        - content: The paragraph text
        - chapter: Chapter number
        - category: Category code (-2 for legality rules, etc.)
        - category_name: Human-readable category name
        - parent_section_fls_id: The parent section's FLS ID
        - is_paragraph: True
    """
    sections_meta, paragraphs_meta = get_fls_metadata(root)
    
    # First check if it's a section-level ID
    if fls_id in sections_meta:
        section_info = sections_meta[fls_id]
        # Load full section content from chapter file
        fls_dir = get_fls_dir(root)
        chapter_num = section_info["chapter"]
        chapter_file = fls_dir / f"chapter_{chapter_num:02d}.json"
        
        chapter = load_json_file(chapter_file)
        if chapter:
            for section in chapter.get("sections", []):
                if section.get("fls_id") == fls_id:
                    result = {
                        "fls_id": fls_id,
                        "title": section.get("title", ""),
                        "content": section.get("content", ""),
                        "chapter": chapter_num,
                        "category": section.get("category", 0),
                        "rubrics": {},
                        "is_paragraph": False,
                    }
                    # Extract rubric paragraphs
                    for cat_code, rubric_data in section.get("rubrics", {}).items():
                        paragraphs = rubric_data.get("paragraphs", {})
                        if paragraphs:
                            result["rubrics"][cat_code] = list(paragraphs.values())
                    return result
    
    # Check if it's a paragraph-level ID
    if fls_id in paragraphs_meta:
        para_info = paragraphs_meta[fls_id]
        return {
            "fls_id": fls_id,
            "title": para_info.get("section_title", ""),
            "content": para_info.get("text", ""),
            "chapter": para_info.get("chapter"),
            "category": para_info.get("category"),
            "category_name": para_info.get("category_name", ""),
            "parent_section_fls_id": para_info.get("section_fls_id"),
            "is_paragraph": True,
        }
    
    return None


def enrich_match_with_fls_content(match: dict, root: Path | None = None) -> dict:
    """
    Enrich a match dict with FLS content.
    
    For section-level IDs: adds fls_content and fls_rubrics fields.
    For paragraph-level IDs: adds fls_content (the paragraph text), 
        fls_category_name, and fls_parent_section fields.
    """
    fls_id = match.get("fls_id")
    if not fls_id:
        return match
    
    fls_data = load_fls_content(fls_id, root)
    if fls_data:
        match = match.copy()
        match["fls_content"] = fls_data.get("content", "")
        match["fls_title"] = fls_data.get("title", match.get("fls_title", ""))
        match["fls_chapter"] = fls_data.get("chapter")
        match["fls_category"] = fls_data.get("category")
        
        if fls_data.get("is_paragraph"):
            # Paragraph-level: include category name and parent info
            match["fls_category_name"] = fls_data.get("category_name", "")
            match["fls_parent_section"] = fls_data.get("parent_section_fls_id")
        else:
            # Section-level: include rubrics
            match["fls_rubrics"] = fls_data.get("rubrics", {})
    return match


# =============================================================================
# Comparison and Flag Computation
# =============================================================================

def normalize_applicability(value: str | None) -> str | None:
    """Normalize applicability values for comparison."""
    if value is None:
        return None
    value = str(value).lower().strip()
    # ADD-6 uses "Yes"/"No"/"Partial", decisions use "yes"/"no"/"partial"
    if value in ("yes", "true", "1"):
        return "yes"
    if value in ("no", "false", "0", "n_a", "n/a"):
        return "no"
    if value in ("partial",):
        return "partial"
    return value


def compute_specificity_decreased(
    mapping_matches: list[dict], decision_matches: list[dict]
) -> tuple[bool, list[dict]]:
    """
    Check if decision lost paragraph-level specificity compared to mapping.
    
    Paragraph-level matches have category != 0 (e.g., -2 for legality rules,
    -3 for dynamic semantics, -4 for undefined behavior). Section-level
    matches have category = 0.
    
    Returns:
        Tuple of (flag_value, lost_paragraphs_details)
        - flag_value: True if specificity decreased
        - lost_paragraphs_details: List of dicts with fls_id, category, title for each lost paragraph
    """
    def get_paragraph_matches(matches: list) -> dict[str, dict]:
        """Get paragraph-level matches (category != 0) as dict keyed by fls_id."""
        result = {}
        for m in matches:
            fls_id = m.get("fls_id")
            category = m.get("category", 0)
            if fls_id and category != 0:
                result[fls_id] = {
                    "fls_id": fls_id,
                    "category": category,
                    "fls_title": m.get("fls_title", ""),
                }
        return result
    
    mapping_paragraphs = get_paragraph_matches(mapping_matches)
    decision_paragraphs = get_paragraph_matches(decision_matches)
    
    # Find lost paragraph IDs
    lost_ids = set(mapping_paragraphs.keys()) - set(decision_paragraphs.keys())
    
    # Build details for lost paragraphs
    lost_details = [mapping_paragraphs[fls_id] for fls_id in sorted(lost_ids)]
    
    # Flag if we lost paragraphs AND ended up with fewer paragraph-level matches
    flag = bool(lost_ids) and len(decision_paragraphs) < len(mapping_paragraphs)
    
    return flag, lost_details


def compute_fls_diff(
    mapping_matches: list[dict], decision_matches: list[dict]
) -> dict[str, Any]:
    """
    Compute FLS ID differences between mapping and decision.
    
    Returns:
        dict with keys: added, removed, retained, specificity_decreased, lost_paragraphs
    """
    mapping_ids: set[str] = {
        str(m.get("fls_id")) for m in mapping_matches if m.get("fls_id")
    }
    decision_ids: set[str] = {
        str(m.get("fls_id")) for m in decision_matches if m.get("fls_id")
    }
    
    # Compute specificity
    specificity_flag, lost_paragraphs = compute_specificity_decreased(
        mapping_matches, decision_matches
    )
    
    return {
        "added": sorted(decision_ids - mapping_ids),
        "removed": sorted(mapping_ids - decision_ids),
        "retained": sorted(mapping_ids & decision_ids),
        "specificity_decreased": specificity_flag,
        "lost_paragraphs": lost_paragraphs,
    }


def compute_comparison(
    mapping_ctx: dict, decision_ctx: dict, add6_ctx: dict | None = None
) -> dict:
    """
    Compute comparison between mapping and decision for one context (all_rust or safe_rust).
    
    Args:
        mapping_ctx: Context data from mapping file
        decision_ctx: Context data from decision file
        add6_ctx: ADD-6 data for this context (applicability, adjusted_category)
    
    Returns:
        Comparison dict with change flags and FLS diffs
    """
    mapping_app = normalize_applicability(mapping_ctx.get("applicability"))
    decision_app = normalize_applicability(decision_ctx.get("applicability"))
    
    mapping_cat = mapping_ctx.get("adjusted_category")
    decision_cat = decision_ctx.get("adjusted_category")
    
    mapping_rat = mapping_ctx.get("rationale_type")
    decision_rat = decision_ctx.get("rationale_type")
    
    fls_diff = compute_fls_diff(
        mapping_ctx.get("accepted_matches", []),
        decision_ctx.get("accepted_matches", []),
    )
    
    comparison = {
        "applicability_changed": mapping_app != decision_app,
        "applicability_mapping_to_decision": f"{mapping_app} → {decision_app}" if mapping_app != decision_app else None,
        "adjusted_category_changed": mapping_cat != decision_cat,
        "adjusted_category_mapping_to_decision": f"{mapping_cat} → {decision_cat}" if mapping_cat != decision_cat else None,
        "rationale_type_changed": mapping_rat != decision_rat,
        "rationale_type_mapping_to_decision": f"{mapping_rat} → {decision_rat}" if mapping_rat != decision_rat else None,
        "fls_added": fls_diff["added"],
        "fls_removed": fls_diff["removed"],
        "fls_retained": fls_diff["retained"],
        "specificity_decreased": fls_diff["specificity_decreased"],
        "lost_paragraphs": fls_diff["lost_paragraphs"],
        "net_fls_change": len(fls_diff["added"]) - len(fls_diff["removed"]),
        "match_count_mapping": len(mapping_ctx.get("accepted_matches", [])),
        "match_count_decision": len(decision_ctx.get("accepted_matches", [])),
        "has_analysis_summary": bool(decision_ctx.get("analysis_summary")),
        "has_search_tools": bool(decision_ctx.get("search_tools_used")),
        "has_rejected_matches": bool(decision_ctx.get("rejected_matches")),
    }
    
    # ADD-6 comparison
    if add6_ctx:
        add6_app = normalize_applicability(add6_ctx.get("applicability"))
        add6_cat = add6_ctx.get("adjusted_category")
        comparison["applicability_differs_from_add6"] = decision_app != add6_app
        comparison["adjusted_category_differs_from_add6"] = decision_cat != add6_cat
    
    return comparison


def compute_flags(
    comparison_all_rust: dict,
    comparison_safe_rust: dict,
    decision: dict,
    batch: int,
) -> dict[str, bool]:
    """
    Compute outlier flags based on comparison data.
    
    Returns dict of flag_name -> bool
    """
    flags = {}
    
    # Applicability differs from ADD-6
    flags["applicability_differs_from_add6"] = (
        comparison_all_rust.get("applicability_differs_from_add6", False)
        or comparison_safe_rust.get("applicability_differs_from_add6", False)
    )
    
    # Adjusted category differs from ADD-6
    flags["adjusted_category_differs_from_add6"] = (
        comparison_all_rust.get("adjusted_category_differs_from_add6", False)
        or comparison_safe_rust.get("adjusted_category_differs_from_add6", False)
    )
    
    # FLS removed (any removal in either context)
    flags["fls_removed"] = (
        len(comparison_all_rust.get("fls_removed", [])) > 0
        or len(comparison_safe_rust.get("fls_removed", [])) > 0
    )
    
    # FLS added (any addition in either context)
    flags["fls_added"] = (
        len(comparison_all_rust.get("fls_added", [])) >= OUTLIER_THRESHOLDS["fls_added"]
        or len(comparison_safe_rust.get("fls_added", [])) >= OUTLIER_THRESHOLDS["fls_added"]
    )
    
    # Specificity decreased (lost paragraph-level matches in either context)
    flags["specificity_decreased"] = (
        comparison_all_rust.get("specificity_decreased", False)
        or comparison_safe_rust.get("specificity_decreased", False)
    )
    
    # Rationale type changed
    flags["rationale_type_changed"] = (
        comparison_all_rust.get("rationale_type_changed", False)
        or comparison_safe_rust.get("rationale_type_changed", False)
    )
    
    # Batch pattern outlier
    flags["batch_pattern_outlier"] = not check_pattern_conformance(
        decision, batch
    )
    
    # Missing analysis summary (v3.1+ expected to have it)
    schema_version = decision.get("schema_version", "")
    if schema_version.startswith("3.1"):
        flags["missing_analysis_summary"] = (
            not comparison_all_rust.get("has_analysis_summary", True)
            or not comparison_safe_rust.get("has_analysis_summary", True)
        )
    else:
        flags["missing_analysis_summary"] = False
    
    # Missing search tools
    flags["missing_search_tools"] = (
        not comparison_all_rust.get("has_search_tools", True)
        or not comparison_safe_rust.get("has_search_tools", True)
    )
    
    # Multi-dimension outlier (2+ flags set)
    active_flags = [k for k, v in flags.items() if v and k != "multi_dimension_outlier"]
    flags["multi_dimension_outlier"] = len(active_flags) >= OUTLIER_THRESHOLDS["multi_dimension"]
    
    return flags


def is_outlier(flags: dict[str, bool]) -> bool:
    """Check if any outlier flag is set."""
    return any(v for k, v in flags.items() if k != "multi_dimension_outlier")


def get_active_flags(flags: dict[str, bool]) -> list[str]:
    """Get list of active (True) flag names."""
    return [k for k, v in flags.items() if v]


# =============================================================================
# Batch Pattern Helpers
# =============================================================================

def get_batch_expected_pattern(batch: int) -> dict:
    """Get expected pattern for a batch."""
    return BATCH_EXPECTED_PATTERNS.get(batch, {"name": f"Batch {batch}", "all_rust": {}, "safe_rust": {}})


def check_pattern_conformance(decision: dict, batch: int) -> bool:
    """
    Check if a decision conforms to expected batch pattern.
    
    Returns True if decision matches expected pattern, False otherwise.
    """
    expected = get_batch_expected_pattern(batch)
    
    for context in ["all_rust", "safe_rust"]:
        expected_ctx = expected.get(context, {})
        
        # Get decision context data
        if is_v2_family(decision):
            decision_ctx = decision.get(context, {})
        else:
            # v1 family: single context
            decision_ctx = decision
        
        # Check each expected field
        for field, expected_value in expected_ctx.items():
            actual_value = decision_ctx.get(field)
            if field == "applicability":
                actual_value = normalize_applicability(actual_value)
                expected_value = normalize_applicability(expected_value)
            if actual_value != expected_value:
                return False
    
    return True


# =============================================================================
# Review State Helpers
# =============================================================================

def recompute_review_summary(root: Path | None = None) -> dict:
    """
    Recompute review summary by scanning all outlier analysis files.
    
    Handles per-context FLS structures: {fls_id: {contexts: [...], decisions: {ctx: {decision, reason}}}}
    
    Returns summary dict for review_state.json.
    """
    outlier_dir = get_outlier_analysis_dir(root)
    
    summary = {
        "total_outliers": 0,
        "fully_reviewed": 0,
        "partially_reviewed": 0,
        "pending": 0,
        "by_aspect": {
            "categorization": {"accepted": 0, "rejected": 0, "pending": 0},
            "fls_removals": {
                "all_rust": {"accepted": 0, "rejected": 0, "pending": 0},
                "safe_rust": {"accepted": 0, "rejected": 0, "pending": 0},
            },
            "fls_additions": {
                "all_rust": {"accepted": 0, "rejected": 0, "pending": 0},
                "safe_rust": {"accepted": 0, "rejected": 0, "pending": 0},
            },
            "specificity": {"accepted": 0, "rejected": 0, "pending": 0},
            "add6_divergence": {"accepted": 0, "rejected": 0, "pending": 0},
        },
    }
    
    if not outlier_dir.exists():
        return summary
    
    for f in outlier_dir.glob("*.json"):
        outlier = load_json_file(f)
        if not outlier:
            continue
        
        summary["total_outliers"] += 1
        
        human_review = outlier.get("human_review", {})
        if not human_review:
            summary["pending"] += 1
            continue
        
        status = human_review.get("overall_status", "pending")
        if status == "fully_reviewed":
            summary["fully_reviewed"] += 1
        elif status == "partial":
            summary["partially_reviewed"] += 1
        else:
            summary["pending"] += 1
        
        # Count by aspect
        cat = human_review.get("categorization", {})
        if cat:
            dec = cat.get("decision")
            if dec == "accept":
                summary["by_aspect"]["categorization"]["accepted"] += 1
            elif dec == "reject":
                summary["by_aspect"]["categorization"]["rejected"] += 1
            else:
                summary["by_aspect"]["categorization"]["pending"] += 1
        
        # FLS removals - per-context structure: {fls_id: {contexts: [...], decisions: {ctx: {...}}}}
        for fls_id, item in human_review.get("fls_removals", {}).items():
            decisions = item.get("decisions", {})
            contexts = item.get("contexts", [])
            for ctx in contexts:
                ctx_dec = decisions.get(ctx, {})
                if isinstance(ctx_dec, dict):
                    dec = ctx_dec.get("decision")
                else:
                    dec = None
                if dec == "accept":
                    summary["by_aspect"]["fls_removals"][ctx]["accepted"] += 1
                elif dec == "reject":
                    summary["by_aspect"]["fls_removals"][ctx]["rejected"] += 1
                else:
                    summary["by_aspect"]["fls_removals"][ctx]["pending"] += 1
        
        # FLS additions - per-context structure
        for fls_id, item in human_review.get("fls_additions", {}).items():
            decisions = item.get("decisions", {})
            contexts = item.get("contexts", [])
            for ctx in contexts:
                ctx_dec = decisions.get(ctx, {})
                if isinstance(ctx_dec, dict):
                    dec = ctx_dec.get("decision")
                else:
                    dec = None
                if dec == "accept":
                    summary["by_aspect"]["fls_additions"][ctx]["accepted"] += 1
                elif dec == "reject":
                    summary["by_aspect"]["fls_additions"][ctx]["rejected"] += 1
                else:
                    summary["by_aspect"]["fls_additions"][ctx]["pending"] += 1
        
        # Specificity
        spec = human_review.get("specificity", {})
        if spec:
            dec = spec.get("decision")
            if dec == "accept":
                summary["by_aspect"]["specificity"]["accepted"] += 1
            elif dec == "reject":
                summary["by_aspect"]["specificity"]["rejected"] += 1
            else:
                summary["by_aspect"]["specificity"]["pending"] += 1
        
        # ADD-6 divergence
        add6 = human_review.get("add6_divergence", {})
        if add6:
            dec = add6.get("decision")
            if dec == "accept":
                summary["by_aspect"]["add6_divergence"]["accepted"] += 1
            elif dec == "reject":
                summary["by_aspect"]["add6_divergence"]["rejected"] += 1
            else:
                summary["by_aspect"]["add6_divergence"]["pending"] += 1
    
    return summary
