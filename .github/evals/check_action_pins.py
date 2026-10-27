"""Fail if an external `uses:` in a GitHub workflow is not pinned to a full commit SHA.

Usage: python .github/evals/check_action_pins.py   (requires PyYAML)
Policy: CONTRIBUTING.md#github-actions-pinning-policy
"""
import pathlib
import re
import sys

import yaml

POLICY = "https://github.com/microsoft/Dataverse-skills/blob/main/CONTRIBUTING.md#github-actions-pinning-policy"
PINNED = re.compile(r"(?!.*\.\.)(?:\./[^@\s]*|[\w.-]+/[\w./-]+@[0-9a-f]{40}|docker://\S+@sha256:[0-9a-f]{64})")


def values(node, key):
    """Every value for `key`; duplicates are kept so a second `uses:` cannot hide."""
    return [v for k, v in node.value if k.value == key] if isinstance(node, yaml.MappingNode) else []


def children(node):
    if isinstance(node, yaml.MappingNode):
        return [v for _, v in node.value]
    return node.value if isinstance(node, yaml.SequenceNode) else []


def uses_nodes(doc):
    """Yield jobs.<id>.uses (reusable workflows) and jobs.<id>.steps[].uses."""
    for job in (j for jobs in values(doc, "jobs") for j in children(jobs)):
        yield from values(job, "uses")
        yield from (u for steps in values(job, "steps") for step in children(steps) for u in values(step, "uses"))


def check(path, rel):
    try:
        doc = yaml.compose(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        return [(rel, getattr(getattr(exc, "problem_mark", None), "line", 0) + 1, f"Invalid YAML: {exc}")]
    return [
        (rel, node.start_mark.line + 1, f"'{node.value}' is not pinned to a full 40-character commit SHA")
        for node in dict.fromkeys(uses_nodes(doc))  # YAML aliases share nodes; report each once
        if not (isinstance(node.value, str) and PINNED.fullmatch(node.value))
    ]


def main(root):
    files = sorted(root.glob(".github/workflows/*.y*ml"))
    errors = [e for p in files for e in check(p, p.relative_to(root).as_posix())]
    for rel, line, msg in errors:
        msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error file={rel},line={line}::{msg}. See {POLICY}")
    print(f"Action pin check: {len(errors)} violation(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[2])))
