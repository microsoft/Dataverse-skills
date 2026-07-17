"""
install-opencode.py — Install Dataverse skills into an opencode-compatible location.

opencode has no plugin marketplace for skill bundles (unlike Claude Code, GitHub
Copilot, Cursor, and Codex, which install this plugin via their own marketplace
commands). opencode instead auto-discovers skills from these locations:

  - .claude/skills/<name>/SKILL.md   (project, Claude Code compatibility layer)
  - ~/.claude/skills/<name>/SKILL.md (global, Claude Code compatibility layer)

This script copies the plugin's skill folders (and scripts/auth.py) from this
repo into one of those locations inside a target project, so opencode picks
them up automatically on its next session. It is idempotent — re-running it
only overwrites files whose content actually changed.

Usage:
    # From a clone of microsoft/Dataverse-skills, targeting the current directory:
    python .github/plugins/dataverse/scripts/install-opencode.py --target /path/to/your/project

    # Install into the global location instead (available in all projects):
    python .github/plugins/dataverse/scripts/install-opencode.py --global

    # Default target is the current working directory:
    python .github/plugins/dataverse/scripts/install-opencode.py

After running, restart (or start a new) opencode session in the target
project — skills are discovered at session startup.
"""

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_SRC = _PLUGIN_ROOT / "skills"
_AUTH_SRC = _PLUGIN_ROOT / "scripts" / "auth.py"


def _copy_tree_if_changed(src: Path, dst: Path) -> list[str]:
    """Copy src into dst recursively, skipping files whose content is unchanged.

    Returns a list of human-readable change descriptions (created/updated).
    """
    changes = []
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        target = dst / item.name
        if item.is_dir():
            changes.extend(_copy_tree_if_changed(item, target))
            continue
        if target.exists() and filecmp.cmp(item, target, shallow=False):
            continue
        action = "updated" if target.exists() else "created"
        shutil.copy2(item, target)
        changes.append(f"{action}: {target}")
    return changes


def install_skills(dest_skills_dir: Path) -> list[str]:
    """Copy every skills/dv-* folder into dest_skills_dir. Returns change log."""
    changes = []
    for skill_dir in sorted(_SKILLS_SRC.glob("dv-*")):
        if not skill_dir.is_dir():
            continue
        changes.extend(_copy_tree_if_changed(skill_dir, dest_skills_dir / skill_dir.name))
    return changes


def install_auth_script(target: Path) -> list[str]:
    """Copy scripts/auth.py into <target>/scripts/auth.py if missing or changed."""
    if not _AUTH_SRC.exists():
        return []
    dest_dir = target / "scripts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "auth.py"
    if dest.exists() and filecmp.cmp(_AUTH_SRC, dest, shallow=False):
        return []
    action = "updated" if dest.exists() else "created"
    shutil.copy2(_AUTH_SRC, dest)
    return [f"{action}: {dest}"]


def main():
    parser = argparse.ArgumentParser(
        description="Install Dataverse skills into an opencode-compatible .claude/skills/ location."
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target project directory (default: current directory). Ignored with --global.",
    )
    parser.add_argument(
        "--global",
        dest="use_global",
        action="store_true",
        help="Install into ~/.claude/skills/ instead of a project's .claude/skills/.",
    )
    args = parser.parse_args()

    if not _SKILLS_SRC.exists():
        print(f"ERROR: skills source directory not found: {_SKILLS_SRC}", file=sys.stderr)
        sys.exit(2)

    if args.use_global:
        target = Path.home()
        dest_skills_dir = target / ".claude" / "skills"
    else:
        target = Path(args.target).resolve()
        dest_skills_dir = target / ".claude" / "skills"

    print(f"Installing Dataverse skills into: {dest_skills_dir}")
    skill_changes = install_skills(dest_skills_dir)

    auth_changes = []
    if not args.use_global:
        auth_changes = install_auth_script(target)

    all_changes = skill_changes + auth_changes
    if not all_changes:
        print("Nothing to do — all files already up to date.")
    else:
        for line in all_changes:
            print(f"  {line}")
        print(f"\n{len(all_changes)} file(s) installed/updated.")

    print(
        "\nDone. Restart (or start a new) opencode session in the target project — "
        "skills are discovered at session startup via .claude/skills/."
    )
    if not args.use_global:
        print(
            "Next: describe what you want in plain English (e.g. \"Connect to Dataverse\") "
            "and the dv-connect skill will handle MCP registration for opencode."
        )


if __name__ == "__main__":
    main()
