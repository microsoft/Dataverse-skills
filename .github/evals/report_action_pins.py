"""Trusted pull_request_target reporter: inspect PR blobs, never execute PR code."""

from __future__ import annotations

import base64
import html
import json
import os
import re
import subprocess
import sys
from urllib.parse import quote

from check_action_pins import Finding, MAX_FILE_BYTES, POLICY_URL, check_yaml, is_candidate

MARKER = "<!-- dataverse-action-pin-policy -->"


def api(endpoint: str, body: dict | None = None, method: str = "GET"):
    command = ["gh", "api", "--hostname", "github.com", "--method", method, endpoint]
    if body is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command, input=json.dumps(body) if body is not None else None,
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(result.stdout)


def comments(repository: str, number: int) -> list[dict]:
    found = []
    page = 1
    while True:
        batch = api(f"repos/{repository}/issues/{number}/comments?per_page=100&page={page}")
        found.extend(batch)
        if len(batch) < 100:
            return found
        page += 1


def scan_head(repository: str, sha: str) -> list[Finding]:
    tree = api(f"repos/{repository}/git/trees/{sha}?recursive=1")
    if tree.get("truncated"):
        raise ValueError("GitHub truncated the tree; refusing an incomplete scan.")
    findings = []
    for entry in tree["tree"]:
        path = entry["path"]
        if not is_candidate(path):
            continue
        if entry["type"] != "blob" or entry["mode"] not in ("100644", "100755"):
            findings.append(Finding(path, 1, "Workflow/action YAML must be a regular file."))
            continue
        if entry["size"] > MAX_FILE_BYTES:
            findings.append(Finding(path, 1, "YAML exceeds the 1 MB validation limit."))
            continue
        blob = api(f"repos/{repository}/git/blobs/{entry['sha']}")
        if blob["encoding"] != "base64":
            raise ValueError("Unexpected GitHub blob encoding.")
        try:
            text = base64.b64decode(blob["content"]).decode("utf-8")
        except UnicodeError:
            findings.append(Finding(path, 1, "YAML must be UTF-8 text."))
            continue
        findings.extend(check_yaml(path, text))
    return findings


def comment_body(repository: str, sha: str, findings: list[Finding]) -> str:
    heading = "Action pinning changes required" if findings else "Action pinning violations resolved"
    lines = [
        MARKER, f"## {heading}", "",
        f"Checked commit [{sha[:12]}](https://github.com/{repository}/commit/{sha}).",
        f"Follow the [GitHub Actions pinning policy]({POLICY_URL}).",
    ]
    if findings:
        lines.extend([
            "", "Replace mutable action/reusable-workflow refs with upstream-verified full",
            "40-character commit SHAs and keep the release tag in a comment.",
            "Docker actions require a SHA-256 digest; local `./` actions are exempt.",
            "", "Run `python .github/evals/check_action_pins.py` before pushing.", "",
        ])
        for finding in findings[:50]:
            url = f"https://github.com/{repository}/blob/{sha}/{quote(finding.path, safe='/')}#L{finding.line}"
            # Show only generated diagnostic text, not attacker-controlled ref values or paths.
            lines.append(f"- [File, line {finding.line}]({url}): {html.escape(finding.message)}")
        if len(findings) > 50:
            lines.append(f"- {len(findings) - 50} more violation(s); run the checker for the full list.")
    else:
        lines.extend(["", "No action pin violations remain. This does not imply that other checks or reviews passed."])
    return "\n".join(lines)


def report(repository: str, number: int, expected_sha: str) -> None:
    endpoint = f"repos/{repository}/pulls/{number}"
    pr = api(endpoint)
    if pr["state"] != "open" or pr["head"]["sha"] != expected_sha:
        print("Skipping closed PR or superseded event.")
        return
    head_repository = pr["head"]["repo"]["full_name"]
    findings = scan_head(head_repository, expected_sha)
    existing = [
        item for item in comments(repository, number)
        if item["user"]["login"] == "github-actions[bot]"
        and item["user"]["type"] == "Bot"
        and item["body"].startswith(MARKER)
    ]
    latest = api(endpoint)
    if latest["state"] != "open" or latest["head"]["sha"] != expected_sha:
        print("PR changed during scan; skipping stale feedback.")
        return
    body = comment_body(head_repository, expected_sha, findings)
    if existing:
        if existing[0]["body"] != body:
            api(f"repos/{repository}/issues/comments/{existing[0]['id']}", {"body": body}, "PATCH")
    elif findings:
        api(f"repos/{repository}/issues/{number}/comments", {"body": body}, "POST")
    print(f"Inspected {expected_sha}: {len(findings)} action pin violation(s).")


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["PR_HEAD_SHA"]
    number = int(os.environ["PR_NUMBER"])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not re.fullmatch(r"[0-9a-f]{40}", sha) or number < 1:
        raise ValueError("Invalid repository, PR number or event head SHA.")
    report(repository, number, sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
