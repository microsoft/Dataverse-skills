"""Validate action refs in this repository's workflows and action manifests.

Run from any directory: python .github/evals/check_action_pins.py
Requires PyYAML, already installed by the Static skill checks job.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

POLICY_URL = (
    "https://github.com/microsoft/Dataverse-skills/blob/main/"
    "CONTRIBUTING.md#github-actions-pinning-policy"
)
MAX_FILE_BYTES = 1_000_000
REMOTE_REF = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-fA-F]{40}")
DOCKER_REF = re.compile(r"docker://[A-Za-z0-9_./:-]+@sha256:[0-9a-fA-F]{64}")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str


def is_candidate(path: str) -> bool:
    parts = PurePosixPath(path).parts
    # Shipped plugin content, including deployment templates, changes only in plugin
    # releases under the version-bump rules, so this CI check excludes it.
    return (
        path.endswith((".yml", ".yaml"))
        and (
            (len(parts) == 3 and parts[:2] == (".github", "workflows"))
            or (parts[-1] in ("action.yml", "action.yaml") and parts[:2] != (".github", "plugins"))
        )
    )


def valid_ref(value: str) -> bool:
    if value == "./":
        return True
    if value.startswith("./"):
        parts = value[2:].split("/")
        return bool(parts) and all(
            part not in ("", ".", "..") and re.fullmatch(r"[A-Za-z0-9_.-]+", part)
            for part in parts
        )
    if REMOTE_REF.fullmatch(value):
        return all(part not in (".", "..") for part in value.split("@")[0].split("/"))
    return bool(DOCKER_REF.fullmatch(value))


def check_yaml(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    visited: set[int] = set()
    mappings: dict[int, dict[str, Node]] = {}
    checked_steps: set[int] = set()
    checked_uses: set[int] = set()

    def fail(node: Node | None, message: str) -> None:
        findings.append(Finding(path, node.start_mark.line + 1 if node else 1, message))

    def mapping(node: Node, label: str) -> dict[str, Node]:
        if not isinstance(node, MappingNode):
            fail(node, f"{label} must be a YAML mapping.")
            return {}
        if id(node) not in mappings:
            mappings[id(node)] = {
                key.value: value for key, value in node.value if isinstance(key, ScalarNode)
            }
        return mappings[id(node)]

    def check_uses(node: Node) -> None:
        if id(node) in checked_uses:
            return
        checked_uses.add(id(node))
        if not isinstance(node, ScalarNode) or node.tag != "tag:yaml.org,2002:str":
            fail(node, "uses must be a literal string.")
        elif not valid_ref(node.value):
            fail(node, "Pin uses to a full 40-character commit SHA (Docker actions need @sha256:<64 hex>); local ./ paths are allowed.")

    def check_steps(node: Node) -> None:
        if id(node) in checked_steps:
            return
        checked_steps.add(id(node))
        if not isinstance(node, SequenceNode):
            fail(node, "steps must be a YAML sequence.")
            return
        for step in node.value:
            fields = mapping(step, "step")
            if "uses" in fields:
                check_uses(fields["uses"])

    def check_structure(node: Node, ancestors: set[int], depth: int = 0) -> None:
        if id(node) in ancestors or depth > 100:
            fail(node, "Recursive aliases or YAML nesting deeper than 100 are not supported.")
            return
        if id(node) in visited:
            return
        visited.add(id(node))
        if node.tag not in {
            f"tag:yaml.org,2002:{kind}"
            for kind in ("map", "seq", "str", "int", "float", "bool", "null", "timestamp")
        }:
            fail(node, "Unsupported YAML tag or merge key; use explicit mappings.")
            return
        if isinstance(node, MappingNode):
            keys: set[str] = set()
            for key, value in node.value:
                if not isinstance(key, ScalarNode):
                    fail(key, "YAML mapping keys must be scalars.")
                elif key.value in keys:
                    fail(key, "Duplicate YAML mapping key.")
                else:
                    keys.add(key.value)
                    check_structure(key, ancestors | {id(node)}, depth + 1)
                check_structure(value, ancestors | {id(node)}, depth + 1)
        elif isinstance(node, SequenceNode):
            for value in node.value:
                check_structure(value, ancestors | {id(node)}, depth + 1)

    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        return [Finding(path, 1, "YAML exceeds the 1 MB validation limit.")]
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError) as exc:
        mark = getattr(exc, "problem_mark", None)
        return [Finding(path, mark.line + 1 if mark else 1, "Malformed YAML; correct the syntax before validating action pins.")]
    if root is None:
        return [Finding(path, 1, "Empty YAML document.")]
    check_structure(root, set())
    if findings:
        return findings
    fields = mapping(root, "document")
    if "jobs" in fields:
        for job in mapping(fields["jobs"], "jobs").values():
            job_fields = mapping(job, "job")
            if "uses" in job_fields:
                check_uses(job_fields["uses"])
            if "steps" in job_fields:
                check_steps(job_fields["steps"])
    elif path.startswith(".github/workflows/"):
        fail(root, "Workflow must contain jobs.")
    if "runs" in fields:
        runs = mapping(fields["runs"], "runs")
        if "steps" in runs:
            check_steps(runs["steps"])
    return findings


def check_files(root: Path) -> list[Finding]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    findings: list[Finding] = []
    for name in sorted(set(result.stdout.split("\0"))):
        if not is_candidate(name):
            continue
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            findings.append(Finding(name, 1, "Workflow/action YAML must be a regular in-repository file."))
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                findings.append(Finding(name, 1, "YAML exceeds the 1 MB validation limit."))
            else:
                findings.extend(check_yaml(name, path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            continue  # git ls-files includes tracked files deleted in the working tree.
        except (OSError, UnicodeError) as exc:
            findings.append(Finding(name, 1, f"Cannot read UTF-8 YAML ({type(exc).__name__})."))
    return findings


def annotation(finding: Finding) -> str:
    def escape(value: str) -> str:
        return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(",", "%2C").replace(":", "%3A")

    return f"::error file={escape(finding.path)},line={finding.line}::{escape(finding.message)} See {POLICY_URL}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        findings = check_files(args.root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Action pin scan failed: {exc}", file=sys.stderr)
        return 2
    for finding in findings:
        print(annotation(finding))
    print(f"Action pin policy: {len(findings)} violation(s). See {POLICY_URL}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
