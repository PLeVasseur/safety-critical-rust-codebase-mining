#!/usr/bin/env python3
"""
Clone iceoryx2 at specified versions into a local cache for FLS mapping analysis.

This script clones the iceoryx2 repository at specified version tags and optionally
the Ferrocene Language Specification (FLS) repository. The output includes a prompt
suitable for providing to an LLM for analysis.

Usage:
    uv run tools/clone_iceoryx2.py --from 0.7.0 --to 0.8.0
    uv run tools/clone_iceoryx2.py --from 0.6.0 --to 0.8.0 --all-versions
    uv run tools/clone_iceoryx2.py --from 0.7.0 --to 0.8.0 --no-fls
    uv run tools/clone_iceoryx2.py --from 0.7.0 --to 0.8.0 --fresh
    uv run tools/clone_iceoryx2.py --from 0.7.0 --to 0.8.0 --full
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


class Version(NamedTuple):
    """Semantic version tuple."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version_str: str) -> Version:
        """Parse a version string like '0.7.0' into a Version tuple."""
        # Strip leading 'v' if present
        version_str = version_str.lstrip("v")
        parts = version_str.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version format: {version_str}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag(self) -> str:
        """Return the git tag for this version."""
        return f"v{self}"


# Repository URLs
ICEORYX2_REPO = "https://github.com/eclipse-iceoryx/iceoryx2.git"
FLS_REPO = "https://github.com/rust-lang/fls.git"


def get_script_dir() -> Path:
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def get_project_root() -> Path:
    """Get the project root directory (parent of tools/)."""
    return get_script_dir().parent


def get_cache_dir() -> Path:
    """Get the cache directory for cloned repositories."""
    return get_project_root() / "cache" / "repos"


def run_git(
    args: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    cmd = ["git"] + args
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def get_available_tags() -> list[str]:
    """Fetch available version tags from the iceoryx2 repository."""
    result = run_git(["ls-remote", "--tags", ICEORYX2_REPO])
    tags = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        # Format: <sha>\trefs/tags/<tag>
        parts = line.split("\t")
        if len(parts) >= 2:
            ref = parts[1]
            if ref.startswith("refs/tags/v") and not ref.endswith("^{}"):
                tag = ref.replace("refs/tags/", "")
                tags.append(tag)
    return sorted(tags, key=lambda t: Version.parse(t))


def validate_version_exists(version: Version, available_tags: list[str]) -> bool:
    """Check if a version tag exists in the available tags."""
    return version.tag in available_tags


def get_versions_in_range(
    from_version: Version,
    to_version: Version,
    available_tags: list[str],
    endpoints_only: bool,
) -> list[Version]:
    """Get all versions in the specified range."""
    if endpoints_only:
        return [from_version, to_version]

    versions = []
    for tag in available_tags:
        version = Version.parse(tag)
        if from_version <= version <= to_version:
            versions.append(version)
    return sorted(versions)


def clone_iceoryx2_version(
    version: Version,
    cache_dir: Path,
    shallow: bool = True,
    fresh: bool = False,
) -> Path:
    """Clone iceoryx2 at a specific version tag."""
    target_dir = cache_dir / "iceoryx2" / version.tag

    if target_dir.exists():
        if fresh:
            print(f"  Removing existing {version.tag}...")
            subprocess.run(["rm", "-rf", str(target_dir)], check=True)
        else:
            print(f"  {version.tag} already exists (use --fresh to re-clone)")
            return target_dir

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    clone_args = ["clone", "--branch", version.tag]
    if shallow:
        clone_args.extend(["--depth", "1"])
    clone_args.extend([ICEORYX2_REPO, str(target_dir)])

    print(f"  Cloning {version.tag}...")
    run_git(clone_args)

    return target_dir


def clone_fls(cache_dir: Path, shallow: bool = True, fresh: bool = False) -> Path:
    """Clone the FLS repository."""
    target_dir = cache_dir / "fls"

    if target_dir.exists():
        if fresh:
            print("  Removing existing FLS...")
            subprocess.run(["rm", "-rf", str(target_dir)], check=True)
        else:
            print("  FLS already exists (use --fresh to re-clone)")
            return target_dir

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    clone_args = ["clone"]
    if shallow:
        clone_args.extend(["--depth", "1"])
    clone_args.extend([FLS_REPO, str(target_dir)])

    print("  Cloning FLS...")
    run_git(clone_args)

    return target_dir


def generate_prompt(
    versions: list[Version],
    iceoryx2_paths: dict[Version, Path],
    fls_path: Path | None,
    project_root: Path,
) -> str:
    """Generate the LLM analysis prompt."""
    lines = [
        "=" * 80,
        "LLM Analysis Prompt",
        "=" * 80,
        "",
        "The following repositories have been checked out for analysis:",
        "",
        "iceoryx2 source code:",
    ]

    for version in versions:
        path = iceoryx2_paths[version]
        lines.append(f"  - {version.tag}: {path}/")

    # Add changelog reference for the newest version
    newest = versions[-1]
    changelog_path = iceoryx2_paths[newest] / "doc" / "release-notes" / f"iceoryx2-{newest.tag}.md"
    if changelog_path.exists():
        lines.append(f"  - Changelog ({newest.tag}): {changelog_path}")

    if fls_path:
        lines.extend(
            [
                "",
                "Ferrocene Language Specification (FLS):",
                f"  - Source: {fls_path}/src/",
                "  - Chapters: general.rst, lexical-elements.rst, items.rst, types-and-traits.rst,",
                "              patterns.rst, expressions.rst, values.rst, statements.rst,",
                "              functions.rst, associated-items.rst, implementations.rst,",
                "              generics.rst, attributes.rst, entities-and-resolution.rst,",
                "              ownership-and-deconstruction.rst, exceptions-and-errors.rst,",
                "              concurrency.rst, program-structure-and-compilation.rst,",
                "              unsafety.rst, macros.rst, ffi.rst, inline-assembly.rst",
                f"  - Changelog: {fls_path}/src/changelog.rst",
            ]
        )

    fls_mapping_path = project_root / "iceoryx2-fls-mapping"
    lines.extend(
        [
            "",
            "Existing FLS mapping JSON files:",
            f"  {fls_mapping_path}/",
            "",
        ]
    )

    # Generate task description based on number of versions
    if len(versions) == 2:
        from_v, to_v = versions
        lines.extend(
            [
                f"Task: Update the FLS mapping from iceoryx2 {from_v.tag} to {to_v.tag}",
                "",
                "Please perform the following:",
                "",
                f"1. Review the iceoryx2 {to_v.tag} changelog for breaking changes and new features",
                "",
                "2. Walk through each FLS chapter (2-22) systematically to:",
                "   a. Verify existing mappings still apply (update file paths, line numbers)",
                "   b. Identify if the new iceoryx2 version uses any FLS-specified constructs",
                "      that were not previously mapped",
                "   c. Check the FLS changelog for any new Rust language features that may",
                "      apply to iceoryx2's code patterns",
                "   d. Update statistics (unsafe counts, atomic usage, FFI calls, etc.)",
                "",
                "3. For each JSON file in iceoryx2-fls-mapping/:",
                f"   a. Update version references from {from_v} to {to_v} in file paths",
                "   b. Update code samples with correct file paths and line numbers",
                f"   c. Add new mappings for features added in {to_v.tag}",
                "   d. Update all statistics counts based on the new source",
                "   e. Remove or update any mappings for code that was removed/refactored",
                "",
                "4. Pay special attention to:",
                "   - Chapter 19 (Unsafety): unsafe blocks, unsafe fn, unsafe impl counts",
                "   - Chapter 17 (Concurrency): Send/Sync impls, atomic usage",
                "   - Chapter 21 (FFI): extern blocks, FFI function counts",
                "   - Any new language constructs used (e.g., unions, new attributes)",
            ]
        )
    else:
        lines.extend(
            [
                f"Task: Analyze FLS mappings across iceoryx2 versions {versions[0].tag} to {versions[-1].tag}",
                "",
                "Multiple versions have been checked out. Please analyze the evolution of",
                "FLS-relevant constructs across these versions.",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone iceoryx2 at specified versions for FLS mapping analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --from 0.7.0 --to 0.8.0
  %(prog)s --from 0.6.0 --to 0.8.0 --all-versions
  %(prog)s --from 0.7.0 --to 0.8.0 --no-fls --fresh
        """,
    )
    parser.add_argument(
        "--from",
        dest="from_version",
        required=True,
        help="Starting version (e.g., 0.7.0)",
    )
    parser.add_argument(
        "--to",
        dest="to_version",
        required=True,
        help="Ending version (e.g., 0.8.0)",
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Clone all versions in range, not just endpoints",
    )
    parser.add_argument(
        "--no-fls",
        action="store_true",
        help="Skip cloning the FLS repository",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Remove and re-clone existing repositories",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Perform full clone instead of shallow clone",
    )

    args = parser.parse_args()

    # Parse versions
    try:
        from_version = Version.parse(args.from_version)
        to_version = Version.parse(args.to_version)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if from_version > to_version:
        print("Error: --from version must be <= --to version", file=sys.stderr)
        return 1

    # Fetch available tags
    print("Fetching available iceoryx2 versions...")
    try:
        available_tags = get_available_tags()
    except subprocess.CalledProcessError as e:
        print(f"Error fetching tags: {e.stderr}", file=sys.stderr)
        return 1

    print(f"  Found {len(available_tags)} versions: {available_tags[0]} to {available_tags[-1]}")

    # Validate versions exist
    if not validate_version_exists(from_version, available_tags):
        print(f"Error: Version {from_version.tag} not found", file=sys.stderr)
        print(f"Available versions: {', '.join(available_tags)}", file=sys.stderr)
        return 1

    if not validate_version_exists(to_version, available_tags):
        print(f"Error: Version {to_version.tag} not found", file=sys.stderr)
        print(f"Available versions: {', '.join(available_tags)}", file=sys.stderr)
        return 1

    # Determine versions to clone
    versions = get_versions_in_range(
        from_version,
        to_version,
        available_tags,
        endpoints_only=not args.all_versions,
    )
    print(f"  Will clone: {', '.join(v.tag for v in versions)}")

    # Clone repositories
    cache_dir = get_cache_dir()
    shallow = not args.full

    print("\nCloning iceoryx2 versions...")
    iceoryx2_paths: dict[Version, Path] = {}
    for version in versions:
        try:
            path = clone_iceoryx2_version(version, cache_dir, shallow=shallow, fresh=args.fresh)
            iceoryx2_paths[version] = path
            print(f"    -> {path}")
        except subprocess.CalledProcessError as e:
            print(f"Error cloning {version.tag}: {e.stderr}", file=sys.stderr)
            return 1

    fls_path = None
    if not args.no_fls:
        print("\nCloning FLS...")
        try:
            fls_path = clone_fls(cache_dir, shallow=shallow, fresh=args.fresh)
            print(f"    -> {fls_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error cloning FLS: {e.stderr}", file=sys.stderr)
            return 1

    # Generate and print the prompt
    print("\n")
    prompt = generate_prompt(versions, iceoryx2_paths, fls_path, get_project_root())
    print(prompt)

    return 0


if __name__ == "__main__":
    sys.exit(main())
