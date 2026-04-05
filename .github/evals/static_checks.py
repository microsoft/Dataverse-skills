"""
Static eval suite for Dataverse plugin skill files.

Checks every SKILL.md for code correctness, auth pattern compliance,
cross-skill completeness, and PAC CLI accuracy. Runs with no external
dependencies (stdlib only).

Usage:
    python .github/evals/static_checks.py
    python .github/evals/static_checks.py --skills-dir path/to/skills

Exit code 0 = all checks passed. Exit code 1 = one or more failures.
"""

import argparse
import re
import sys
from pathlib import Path

# Skills that intentionally have no Skill Boundaries table.
NO_BOUNDARIES_EXEMPT = {"dv-overview", "dv-connect"}


def extract_fenced_blocks(text, lang="python"):
    """Return list of (block_index, content) for fenced blocks of the given lang."""
    pattern = rf"```{re.escape(lang)}\n(.*?)```" if lang else r"```\w*\n(.*?)```"
    return list(enumerate(re.findall(pattern, text, re.DOTALL), start=1))


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    name = path.parent.name
    failures = []

    python_blocks = extract_fenced_blocks(text, "python")
    bash_blocks = extract_fenced_blocks(text, "bash") + extract_fenced_blocks(text, "sh")
    # Also catch unlabelled fenced blocks that contain pac commands
    unlabelled = extract_fenced_blocks(text, "")

    for i, block in python_blocks:
        label = f"{name} python-block-{i}"

        # EVAL-AUTH-01: no 'from scripts.auth import'
        if "from scripts.auth import" in block:
            failures.append(
                f"EVAL-AUTH-01 [{label}] 'from scripts.auth import' is wrong -- "
                f"use sys.path.insert + 'from auth import'"
            )

        # EVAL-PY-01: sys.path.insert must precede 'from auth import'
        if "from auth import" in block:
            lines = block.splitlines()
            auth_idx = next((j for j, l in enumerate(lines) if "from auth import" in l), None)
            path_idx = next((j for j, l in enumerate(lines) if "sys.path.insert" in l), None)
            if path_idx is None:
                failures.append(
                    f"EVAL-PY-01 [{label}] 'from auth import' present but no sys.path.insert"
                )
            elif path_idx > auth_idx:
                failures.append(
                    f"EVAL-PY-01 [{label}] sys.path.insert appears after 'from auth import'"
                )

        # EVAL-PY-04: no all-comment stub blocks
        non_blank = [l for l in block.splitlines() if l.strip()]
        if non_blank and all(l.strip().startswith("#") for l in non_blank):
            failures.append(
                f"EVAL-PY-04 [{label}] block is all comments -- "
                f"replace stub with runnable code or remove the python fence"
            )

        # EVAL-PY-05 / EVAL-AUTH-03: get_token() must not appear in SDK blocks
        if "DataverseClient(" in block and "get_token" in block:
            failures.append(
                f"EVAL-PY-05 [{label}] get_token() used in block containing DataverseClient() -- "
                f"use get_credential() for SDK operations"
            )

        # EVAL-PY-06: load_env() must precede os.environ access (except notebook blocks)
        if "os.environ[" in block and "load_env" not in block:
            if "InteractiveBrowserCredential" not in block:
                failures.append(
                    f"EVAL-PY-06 [{label}] os.environ accessed without calling load_env() first"
                )

    # EVAL-PAC-02: pac --version must not appear anywhere
    for i, block in bash_blocks + unlabelled:
        if "pac --version" in block:
            failures.append(
                f"EVAL-PAC-02 [{name}] 'pac --version' found -- "
                f"use 'pac' (banner) to check installation, not 'pac --version'"
            )
            break  # one report per file is enough

    # EVAL-COMPLETE-01: Skill Boundaries table required
    if name not in NO_BOUNDARIES_EXEMPT:
        has_boundaries = re.search(r"^##\s+skill boundaries", text, re.IGNORECASE | re.MULTILINE)
        if not has_boundaries:
            failures.append(
                f"EVAL-COMPLETE-01 [{name}] missing '## Skill boundaries' section"
            )

    return failures


def main():
    parser = argparse.ArgumentParser(description="Static evals for Dataverse skill files")
    parser.add_argument(
        "--skills-dir",
        default=".github/plugins/dataverse/skills",
        help="Path to the skills directory (default: .github/plugins/dataverse/skills)",
    )
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.exists():
        print(f"ERROR: skills directory not found: {skills_dir}", file=sys.stderr)
        sys.exit(2)

    skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_files:
        print(f"ERROR: no SKILL.md files found under {skills_dir}", file=sys.stderr)
        sys.exit(2)

    all_failures = []
    python_block_count = 0

    for f in skill_files:
        text = f.read_text(encoding="utf-8")
        python_block_count += len(re.findall(r"```python\n", text))
        failures = check_file(f)
        all_failures.extend(failures)

    if all_failures:
        print(f"FAILED -- {len(all_failures)} issue(s) across {len(skill_files)} skill files:\n")
        for failure in all_failures:
            print(f"  FAIL  {failure}")
        sys.exit(1)
    else:
        print(
            f"PASSED -- {len(skill_files)} skill files, "
            f"{python_block_count} Python blocks checked"
        )


if __name__ == "__main__":
    main()
