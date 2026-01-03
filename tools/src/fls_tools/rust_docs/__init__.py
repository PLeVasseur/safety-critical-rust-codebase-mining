"""
Rust Documentation Infrastructure

This package provides tools for cloning, extracting, and searching
Rust documentation sources to enrich MISRA-to-FLS verification:

- Rust Reference: Authoritative language reference
- Unsafe Code Guidelines (UCG): Formal unsafe semantics
- Rustonomicon: Practical unsafe Rust guide
- Clippy: ~700 lints with descriptions

Tools:
- clone-rust-docs: Clone/update documentation repositories
- extract-reference: Extract Reference content to JSON
- extract-ucg: Extract UCG content to JSON
- extract-nomicon: Extract Nomicon content to JSON
- extract-clippy-lints: Extract Clippy lint metadata to JSON
- generate-rust-embeddings: Generate embeddings for extracted content
- search-rust-context: Search across all sources for MISRA context
"""

from .clone import RUST_DOC_SOURCES

__all__ = [
    "RUST_DOC_SOURCES",
]
