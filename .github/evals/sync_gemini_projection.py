# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Generate or verify the Gemini CLI root compatibility projection."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTIONS = {
    REPO_ROOT / ".github" / "plugins" / "dataverse" / "skills": REPO_ROOT / "skills",
    REPO_ROOT / ".github" / "plugins" / "dataverse" / "scripts": REPO_ROOT / "scripts",
}
IGNORED_NAMES = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _is_ignored(relative_path: Path) -> bool:
    return any(
        part in IGNORED_NAMES or Path(part).suffix in IGNORED_SUFFIXES
        for part in relative_path.parts
    )


def _symlinks(root: Path) -> list[Path]:
    return [path.relative_to(root) for path in root.rglob("*") if path.is_symlink()]


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORED_NAMES or Path(name).suffix in IGNORED_SUFFIXES
    }


def _projected_files(root: Path) -> dict[Path, Path]:
    """Return relative paths mapped to source files included in a projection."""
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file()
        and not _is_ignored(path.relative_to(root))
    }


def _projection_differences(source: Path, target: Path) -> list[str]:
    source_files = _projected_files(source)
    target_files = _projected_files(target) if target.is_dir() else {}
    differences = []

    for relative_path in sorted(source_files.keys() - target_files.keys()):
        differences.append(f"missing: {target.name}/{relative_path.as_posix()}")
    for relative_path in sorted(target_files.keys() - source_files.keys()):
        differences.append(f"extra: {target.name}/{relative_path.as_posix()}")
    for relative_path in sorted(source_files.keys() & target_files.keys()):
        if not filecmp.cmp(
            source_files[relative_path], target_files[relative_path], shallow=False
        ):
            differences.append(f"changed: {target.name}/{relative_path.as_posix()}")

    return differences


def check_projection() -> list[str]:
    differences = []
    for source, target in PROJECTIONS.items():
        if not source.is_dir():
            differences.append(f"canonical source missing: {source}")
            continue
        source_symlinks = _symlinks(source)
        if source_symlinks:
            differences.extend(
                f"canonical symlink not allowed: {source.name}/{path.as_posix()}"
                for path in source_symlinks
            )
            continue
        if not target.is_dir() or target.is_symlink():
            differences.append(f"projection directory missing or invalid: {target.name}/")
            continue
        target_symlinks = _symlinks(target)
        if target_symlinks:
            differences.extend(
                f"projection symlink not allowed: {target.name}/{path.as_posix()}"
                for path in target_symlinks
            )
            continue
        differences.extend(_projection_differences(source, target))
    return differences


def sync_projection() -> None:
    for source, target in PROJECTIONS.items():
        if not source.is_dir():
            raise FileNotFoundError(f"Canonical projection source not found: {source}")
        source_symlinks = _symlinks(source)
        if source_symlinks:
            paths = ", ".join(path.as_posix() for path in source_symlinks)
            raise RuntimeError(f"Canonical projection source contains symlinks: {paths}")
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.copytree(
            source,
            target,
            ignore=_copy_ignore,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify Gemini CLI root skills/scripts projections."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the root projection differs from the canonical plugin payload.",
    )
    args = parser.parse_args()

    if not args.check:
        sync_projection()

    differences = check_projection()
    if differences:
        print("Gemini projection is out of date:", file=sys.stderr)
        for difference in differences:
            print(f"  {difference}", file=sys.stderr)
        print(
            "Run: python .github/evals/sync_gemini_projection.py",
            file=sys.stderr,
        )
        return 1

    action = "verified" if args.check else "generated"
    print(f"Gemini projection {action}: skills/ and scripts/ match canonical sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())