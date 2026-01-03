#!/usr/bin/env python3
"""
clone-rust-docs: Clone/update Rust documentation repositories.

This tool manages local clones of Rust documentation sources used
for enriching MISRA-to-FLS verification:

- Rust Reference: Authoritative language reference
- Unsafe Code Guidelines (UCG): Formal unsafe semantics  
- Rustonomicon: Practical unsafe Rust guide
- Clippy: ~700 lints with descriptions

Usage:
    uv run clone-rust-docs                     # Clone/update all sources
    uv run clone-rust-docs --source reference  # Clone specific source
    uv run clone-rust-docs --source all        # Explicit all
    uv run clone-rust-docs --list              # List sources and status
    uv run clone-rust-docs --update            # Update existing clones only
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import get_project_root, get_cache_dir


# Repository definitions
RUST_DOC_SOURCES = {
    "reference": {
        "repo": "https://github.com/rust-lang/reference.git",
        "path": "reference",
        "description": "Rust Reference - authoritative language reference",
        "content_path": "src",  # Where markdown content lives
    },
    "ucg": {
        "repo": "https://github.com/rust-lang/unsafe-code-guidelines.git",
        "path": "unsafe-code-guidelines",
        "description": "Unsafe Code Guidelines - formal unsafe semantics",
        "content_path": "reference/src",
    },
    "nomicon": {
        "repo": "https://github.com/rust-lang/nomicon.git",
        "path": "nomicon",
        "description": "Rustonomicon - practical unsafe Rust guide",
        "content_path": "src",
    },
    "clippy": {
        "repo": "https://github.com/rust-lang/rust-clippy.git",
        "path": "rust-clippy",
        "description": "Clippy - ~700 lints with descriptions",
        "content_path": "clippy_lints/src",
    },
}

VALID_SOURCES = list(RUST_DOC_SOURCES.keys()) + ["all"]


def get_docs_cache_dir(root: Path) -> Path:
    """Get the cache directory for Rust documentation."""
    return get_cache_dir(root) / "docs"


def get_source_path(root: Path, source_name: str) -> Path:
    """Get the local path for a documentation source."""
    source = RUST_DOC_SOURCES[source_name]
    return get_docs_cache_dir(root) / source["path"]


def get_git_info(repo_path: Path) -> dict | None:
    """Get git information for a repository."""
    if not (repo_path / ".git").exists():
        return None
    
    try:
        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commit = result.stdout.strip()[:12]
        
        # Get commit date
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_date = result.stdout.strip()
        
        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        
        return {
            "commit": commit,
            "commit_date": commit_date,
            "branch": branch,
        }
    except subprocess.CalledProcessError:
        return None


def clone_source(root: Path, source_name: str, update_only: bool = False) -> bool:
    """
    Clone or update a documentation source.
    
    Args:
        root: Project root directory
        source_name: Name of the source to clone
        update_only: If True, only update existing clones (don't clone new)
    
    Returns:
        True if successful, False otherwise
    """
    source = RUST_DOC_SOURCES[source_name]
    target_path = get_source_path(root, source_name)
    
    if target_path.exists() and (target_path / ".git").exists():
        # Repository exists - update it
        print(f"Updating {source_name}...")
        try:
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=target_path,
                capture_output=True,
                text=True,
                check=True,
            )
            git_info = get_git_info(target_path)
            if git_info:
                print(f"  Updated to {git_info['commit']} ({git_info['branch']})")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: Failed to update: {e.stderr}", file=sys.stderr)
            return False
    
    elif update_only:
        # Skip if update_only and repo doesn't exist
        print(f"Skipping {source_name} (not cloned, --update specified)")
        return True
    
    else:
        # Clone new repository
        print(f"Cloning {source_name}...")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", source["repo"], str(target_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            git_info = get_git_info(target_path)
            if git_info:
                print(f"  Cloned at {git_info['commit']} ({git_info['branch']})")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: Failed to clone: {e.stderr}", file=sys.stderr)
            return False


def list_sources(root: Path) -> None:
    """List all documentation sources and their status."""
    print("=" * 70)
    print("RUST DOCUMENTATION SOURCES")
    print("=" * 70)
    print()
    
    for name, source in RUST_DOC_SOURCES.items():
        path = get_source_path(root, name)
        print(f"{name}:")
        print(f"  Description: {source['description']}")
        print(f"  Repository:  {source['repo']}")
        print(f"  Local path:  {path.relative_to(root)}")
        
        if path.exists() and (path / ".git").exists():
            git_info = get_git_info(path)
            if git_info:
                print(f"  Status:      CLONED")
                print(f"  Commit:      {git_info['commit']}")
                print(f"  Branch:      {git_info['branch']}")
                print(f"  Date:        {git_info['commit_date']}")
            else:
                print(f"  Status:      CLONED (git info unavailable)")
        else:
            print(f"  Status:      NOT CLONED")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Clone/update Rust documentation repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run clone-rust-docs                     # Clone/update all
    uv run clone-rust-docs --source reference  # Clone specific source
    uv run clone-rust-docs --list              # Show status
    uv run clone-rust-docs --update            # Update existing only
        """,
    )
    parser.add_argument(
        "--source", "-s",
        type=str,
        choices=VALID_SOURCES,
        default="all",
        help="Source to clone (default: all)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all sources and their status",
    )
    parser.add_argument(
        "--update", "-u",
        action="store_true",
        help="Only update existing clones, don't clone new",
    )
    
    args = parser.parse_args()
    root = get_project_root()
    
    if args.list:
        list_sources(root)
        return
    
    # Determine which sources to process
    if args.source == "all":
        sources = list(RUST_DOC_SOURCES.keys())
    else:
        sources = [args.source]
    
    print(f"Processing {len(sources)} source(s)...")
    print()
    
    success_count = 0
    fail_count = 0
    
    for source_name in sources:
        if clone_source(root, source_name, update_only=args.update):
            success_count += 1
        else:
            fail_count += 1
    
    print()
    print("-" * 40)
    print(f"Done: {success_count} succeeded, {fail_count} failed")
    
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
