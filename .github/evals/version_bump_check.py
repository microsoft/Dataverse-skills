"""
Version bump check — compares the base branch to HEAD and verifies that the
version bump in the PR matches what the structural changes require.

Rules:
  - A removed or renamed skill directory requires a MAJOR bump.
  - A new skill directory requires a MINOR bump (or MAJOR).
  - Modifications only (prose, code fixes) can be PATCH.

Usage:
    python .github/evals/version_bump_check.py [--base main]

Exit codes:
  0 = check passed (or nothing version-relevant changed)
  1 = version bump violates required level
  2 = script error (missing git, not in repo, etc.)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILLS_REL = ".github/plugins/dataverse/skills"
VERSION_FILE_REL = ".github/plugins/dataverse/.claude-plugin/plugin.json"

BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def run_git(args):
    """Run a git command, return stdout (stripped). Raise on non-zero exit."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def parse_semver(v):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", v.strip())
    if not m:
        raise ValueError(f"not valid semver: {v!r}")
    return tuple(int(p) for p in m.groups())


def classify_bump(old, new):
    """Return 'major', 'minor', 'patch', or 'none' given two semver tuples."""
    if new == old:
        return "none"
    if new[0] != old[0]:
        return "major"
    if new[1] != old[1]:
        return "minor"
    return "patch"


def get_version_at(ref, path):
    """Read the plugin.json version at the given git ref. None if file missing."""
    try:
        content = run_git(["show", f"{ref}:{path}"])
    except RuntimeError:
        return None
    try:
        return json.loads(content).get("version")
    except json.JSONDecodeError:
        return None


def get_head_version(repo_root):
    path = repo_root / VERSION_FILE_REL
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("version")


def list_skills_at(ref, skills_rel):
    """List skill directory names at the given git ref."""
    try:
        out = run_git(["ls-tree", "-d", "--name-only", f"{ref}:{skills_rel}"])
    except RuntimeError:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def list_head_skills(repo_root):
    skills_dir = repo_root / SKILLS_REL
    if not skills_dir.exists():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def required_bump(added, removed):
    if removed:
        return "major"
    if added:
        return "minor"
    return "patch"


def main():
    parser = argparse.ArgumentParser(description="Verify plugin version bump matches structural changes")
    parser.add_argument("--base", default="main", help="base branch to compare against (default: main)")
    args = parser.parse_args()

    try:
        repo_root = Path(run_git(["rev-parse", "--show-toplevel"]))
    except RuntimeError as e:
        print(f"ERROR: not in a git repository: {e}", file=sys.stderr)
        sys.exit(2)

    # Fetch base branch if not already available locally (no-op if already fetched)
    try:
        run_git(["rev-parse", "--verify", args.base])
    except RuntimeError:
        try:
            run_git(["fetch", "origin", args.base])
        except RuntimeError as e:
            print(f"ERROR: cannot access base branch '{args.base}': {e}", file=sys.stderr)
            sys.exit(2)

    base_ref = args.base
    base_version = get_version_at(base_ref, VERSION_FILE_REL)
    head_version = get_head_version(repo_root)

    if base_version is None:
        print(f"ERROR: could not read version from {base_ref}:{VERSION_FILE_REL}", file=sys.stderr)
        sys.exit(2)
    if head_version is None:
        print(f"ERROR: could not read version from HEAD:{VERSION_FILE_REL}", file=sys.stderr)
        sys.exit(2)

    try:
        old = parse_semver(base_version)
        new = parse_semver(head_version)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    declared = classify_bump(old, new)

    base_skills = list_skills_at(base_ref, SKILLS_REL)
    head_skills = list_head_skills(repo_root)
    added = head_skills - base_skills
    removed = base_skills - head_skills

    required = required_bump(added, removed)

    # If nothing structural changed and declared is 'none', that's fine (PR may
    # not need a bump at all — e.g., doc-only changes outside skills/).
    if required == "patch" and declared == "none":
        print("PASSED -- no version bump needed (no structural skill changes)")
        sys.exit(0)

    if BUMP_RANK[declared] < BUMP_RANK[required]:
        print(
            f"FAILED -- version bump insufficient\n"
            f"  base ({base_ref}):  {base_version}\n"
            f"  head (current):  {head_version}\n"
            f"  declared bump:   {declared}\n"
            f"  required bump:   {required}\n"
        )
        if added:
            print(f"  added skills:    {sorted(added)}")
        if removed:
            print(f"  removed skills:  {sorted(removed)}")
        print(
            f"\nBump the version to at least {required.upper()} level "
            f"(see CLAUDE.md 'Semver rules' section)."
        )
        sys.exit(1)

    msg = (
        f"PASSED -- {base_version} -> {head_version} "
        f"({declared} bump, {required} required)"
    )
    if added:
        msg += f"\n  added skills: {sorted(added)}"
    if removed:
        msg += f"\n  removed skills: {sorted(removed)}"
    print(msg)

    # Warn on over-bumping (declared > required) when no structural changes were
    # detected. Legitimate cases exist (auth pattern change, renamed sections,
    # new capabilities inside a skill), but a mismatch is worth a reviewer's eye.
    if BUMP_RANK[declared] > BUMP_RANK[required] and not added and not removed:
        print(
            f"\nWARN -- declared {declared.upper()} bump but no structural skill "
            f"changes detected.\n"
            f"       Verify this is intentional (e.g., auth pattern change, "
            f"renamed required section,\n"
            f"       or other breaking change not reflected in skill directory "
            f"structure)."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
