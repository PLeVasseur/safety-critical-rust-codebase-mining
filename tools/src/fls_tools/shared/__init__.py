"""
Shared utilities for FLS mapping tools.

This package provides cross-cutting utilities used by both pipelines:
- Pipeline 1: iceoryx2 -> FLS mapping
- Pipeline 2: MISRA/CERT -> FLS mapping

Modules:
- paths: Project root and common path utilities
- constants: Shared constants (CATEGORY_NAMES, thresholds, etc.)
- io: JSON and embedding I/O utilities
- fls: FLS chapter loading and metadata utilities
- similarity: Cosine similarity and search utilities

All verification and embedding tools require a --standard parameter.
Valid standards: misra-c, misra-cpp, cert-c, cert-cpp
"""

from .paths import (
    # Standard name utilities
    VALID_STANDARDS,
    STANDARD_CLI_TO_INTERNAL,
    normalize_standard,
    cli_standard,
    # Directory helpers
    get_project_root,
    get_tools_dir,
    get_data_dir,
    get_cache_dir,
    get_coding_standards_dir,
    get_mappings_dir,
    get_standards_definitions_dir,
    get_embeddings_dir,
    get_iceoryx2_fls_dir,
    get_repos_cache_dir,
    get_fls_repo_dir,
    get_iceoryx2_repo_dir,
    # FLS paths (shared across standards)
    get_fls_dir,
    get_fls_index_path,
    get_fls_chapter_path,
    get_fls_section_embeddings_path,
    get_fls_paragraph_embeddings_path,
    get_fls_section_mapping_path,
    get_fls_id_to_section_path,
    get_synthetic_fls_ids_path,
    # Standard-specific paths (parameterized)
    get_standard_embeddings_dir,
    get_standard_mappings_path,
    get_standard_definitions_path,
    get_standard_extracted_text_path,
    get_standard_similarity_path,
    get_standard_embeddings_path,
    get_standard_query_embeddings_path,
    get_standard_rationale_embeddings_path,
    get_standard_amplification_embeddings_path,
    get_standard_pdf_path,
    # Verification paths (parameterized)
    get_verification_dir,
    get_verification_progress_path,
    get_verification_cache_dir,
    get_batch_report_path,
    get_batch_decisions_dir,
    # Other shared paths
    get_concept_to_fls_path,
    get_misra_rust_applicability_path,
    # Path resolution and validation
    resolve_path,
    validate_path_in_project,
    PathOutsideProjectError,
)

from .constants import (
    CATEGORY_CODES,
    CATEGORY_NAMES,
    DEFAULT_SECTION_THRESHOLD,
    DEFAULT_PARAGRAPH_THRESHOLD,
    CONCEPT_BOOST_ADDITIVE,
    CONCEPT_ONLY_BASE_SCORE,
    SEE_ALSO_SCORE_PENALTY,
    SEE_ALSO_MAX_MATCHES,
)

from .io import (
    load_json,
    save_json,
    load_embeddings,
)

from .fls import (
    load_fls_chapters,
    build_fls_metadata,
)

from .similarity import (
    cosine_similarity_vector,
    search_embeddings,
)

from .search_id import (
    generate_search_id,
    validate_search_id,
)

from .schema_version import (
    SchemaVersion,
    detect_schema_version,
    is_v1,
    is_v2,
    get_guideline_schema_version,
    get_decision_schema_version,
    get_progress_schema_version,
    get_batch_report_schema_version,
    convert_v1_applicability_to_v2,
    convert_v2_applicability_to_v1,
    normalize_rationale_type,
)

from .fls_ids import (
    get_valid_fls_ids_path,
    generate_valid_fls_ids,
    load_valid_fls_ids,
    validate_fls_id,
)

__all__ = [
    # Standard name utilities
    "VALID_STANDARDS",
    "STANDARD_CLI_TO_INTERNAL",
    "normalize_standard",
    "cli_standard",
    # paths - directories
    "get_project_root",
    "get_tools_dir",
    "get_data_dir",
    "get_cache_dir",
    "get_coding_standards_dir",
    "get_mappings_dir",
    "get_standards_definitions_dir",
    "get_embeddings_dir",
    "get_iceoryx2_fls_dir",
    "get_repos_cache_dir",
    "get_fls_repo_dir",
    "get_iceoryx2_repo_dir",
    # paths - FLS (shared)
    "get_fls_dir",
    "get_fls_index_path",
    "get_fls_chapter_path",
    "get_fls_section_embeddings_path",
    "get_fls_paragraph_embeddings_path",
    "get_fls_section_mapping_path",
    "get_fls_id_to_section_path",
    "get_synthetic_fls_ids_path",
    # paths - standard-specific (parameterized)
    "get_standard_embeddings_dir",
    "get_standard_mappings_path",
    "get_standard_definitions_path",
    "get_standard_extracted_text_path",
    "get_standard_similarity_path",
    "get_standard_embeddings_path",
    "get_standard_query_embeddings_path",
    "get_standard_rationale_embeddings_path",
    "get_standard_amplification_embeddings_path",
    "get_standard_pdf_path",
    # paths - verification (parameterized)
    "get_verification_dir",
    "get_verification_progress_path",
    "get_verification_cache_dir",
    "get_batch_report_path",
    "get_batch_decisions_dir",
    # paths - other shared
    "get_concept_to_fls_path",
    "get_misra_rust_applicability_path",
    # paths - resolution and validation
    "resolve_path",
    "validate_path_in_project",
    "PathOutsideProjectError",
    # constants
    "CATEGORY_CODES",
    "CATEGORY_NAMES",
    "DEFAULT_SECTION_THRESHOLD",
    "DEFAULT_PARAGRAPH_THRESHOLD",
    "CONCEPT_BOOST_ADDITIVE",
    "CONCEPT_ONLY_BASE_SCORE",
    "SEE_ALSO_SCORE_PENALTY",
    "SEE_ALSO_MAX_MATCHES",
    # io
    "load_json",
    "save_json",
    "load_embeddings",
    # fls
    "load_fls_chapters",
    "build_fls_metadata",
    # similarity
    "cosine_similarity_vector",
    "search_embeddings",
    # search_id
    "generate_search_id",
    "validate_search_id",
    # schema_version
    "SchemaVersion",
    "detect_schema_version",
    "is_v1",
    "is_v2",
    "get_guideline_schema_version",
    "get_decision_schema_version",
    "get_progress_schema_version",
    "get_batch_report_schema_version",
    "convert_v1_applicability_to_v2",
    "convert_v2_applicability_to_v1",
    "normalize_rationale_type",
    # fls_ids
    "get_valid_fls_ids_path",
    "generate_valid_fls_ids",
    "load_valid_fls_ids",
    "validate_fls_id",
]
