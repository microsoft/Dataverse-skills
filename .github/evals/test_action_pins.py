"""Hermetic regression tests for SHA enforcement and trusted PR feedback."""

import base64
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

import check_action_pins as checker
import report_action_pins as reporter

SHA = "a" * 40
WORKFLOW = ".github/workflows/test.yml"


def workflow(ref):
    return f"name: test\non: push\njobs:\n  test:\n    steps:\n      - uses: {ref}\n"


class PinTests(unittest.TestCase):
    def test_external_pin_and_subdirectory(self):
        for ref in (f"actions/checkout@{SHA}", f"github/codeql-action/init@{SHA}", f"'a/b@{SHA}' # v1"):
            with self.subTest(ref=ref):
                self.assertEqual([], checker.check_yaml(WORKFLOW, workflow(ref)))

    def test_mutable_and_invalid_refs(self):
        for ref in ("a/b@v1", "a/b@main", "a/b@v1.2.3", "a/b@abc1234",
                    f"a/b@{SHA}a", "a/b@" + "g" * 40, "${{ inputs.action }}",
                    "null", "true", "123", "[]", "{}", "'./../escape'",
                    "'./action@main'", "'./${{ inputs.path }}'", "'a/../b@" + SHA + "'"):
            with self.subTest(ref=ref):
                findings = checker.check_yaml(WORKFLOW, workflow(ref))
                self.assertEqual(1, len(findings))
                self.assertEqual(6, findings[0].line)

    def test_local_and_docker(self):
        for ref in ("./.github/actions/build", "./.github/workflows/build.yml",
                    "docker://ghcr.io/org/image@sha256:" + "a" * 64):
            self.assertEqual([], checker.check_yaml(WORKFLOW, workflow(ref)))
        for ref in ("docker://alpine:3", "docker://alpine@sha256:1234"):
            self.assertTrue(checker.check_yaml(WORKFLOW, workflow(ref)))

    def test_root_local_action(self):
        self.assertTrue(checker.valid_ref("./"))
        self.assertEqual([], checker.check_yaml(WORKFLOW, workflow("./")))
        text = "runs:\n  using: composite\n  steps:\n    - uses: ./\n"
        self.assertEqual([], checker.check_yaml("actions/example/action.yaml", text))

    def test_reusable_workflows(self):
        for ref, count in ((f"org/repo/.github/workflows/build.yml@{SHA}", 0),
                           ("org/repo/.github/workflows/build.yml@main", 1),
                           ("./.github/workflows/build.yml", 0)):
            text = f"jobs:\n  reusable:\n    uses: {ref}\n"
            self.assertEqual(count, len(checker.check_yaml(WORKFLOW, text)))

    def test_composite_action(self):
        text = "runs:\n  using: composite\n  steps:\n    - uses: a/b@v1\n"
        self.assertEqual(4, checker.check_yaml("actions/example/action.yaml", text)[0].line)

    def test_non_executable_uses_text_is_ignored(self):
        text = "jobs:\n  test:\n    env:\n      uses: data\n    steps:\n      - run: |\n          echo 'uses: a/b@v1'\n# uses: a/b@v1\n"
        self.assertEqual([], checker.check_yaml(WORKFLOW, text))

    def test_scope(self):
        for path in (WORKFLOW, ".github/workflows/test.yaml", "action.yml",
                     "src/actions/build/action.yaml", ".github/plugins/dataverse/templates/deploy.yml",
                     ".github/plugins/other/templates/nested/deploy.yaml"):
            self.assertTrue(checker.is_candidate(path), path)
        for path in ("README.md", ".github/dependabot.yml", "docs/example.yml",
                     ".github/workflows/nested/not-a-workflow.yml", "unrelated/templates/data.yaml"):
            self.assertFalse(checker.is_candidate(path), path)

    def test_yaml_errors_and_shapes(self):
        for text in ("", "jobs: [", "---\njobs: {}\n---\njobs: {}",
                     "jobs: {}\njobs: {}", "jobs: {a: {steps: null}}",
                     "jobs: {a: {steps: [null]}}", "jobs: {a: null}",
                     "jobs: []", "jobs: {a: {steps: [{uses: x, uses: y}]}}",
                     "jobs: {a: {<<: {steps: []}}}", "jobs: !unknown {}",
                     "jobs: &recursive {a: *recursive}", "[not, a, workflow]"):
            with self.subTest(text=text):
                self.assertTrue(checker.check_yaml(WORKFLOW, text))

    def test_aliases(self):
        text = "jobs:\n  a: &job\n    steps:\n      - uses: a/b@v1\n  b: *job\n"
        findings = checker.check_yaml(WORKFLOW, text)
        self.assertEqual(1, len(findings))
        self.assertEqual(4, findings[0].line)

    def test_shared_jobs_and_steps_are_validated_once(self):
        text = "jobs:\n  a: &job\n    steps:\n      - &step {uses: a/b@" + SHA + "}\n"
        text += "      - *step\n" * 49
        text += "".join(f"  job{i}: *job\n" for i in range(49))
        with patch.object(checker, "valid_ref", wraps=checker.valid_ref) as valid:
            self.assertEqual([], checker.check_yaml(WORKFLOW, text))
            valid.assert_called_once()

    def test_large_and_deep_yaml(self):
        self.assertTrue(checker.check_yaml(WORKFLOW, "#" * (checker.MAX_FILE_BYTES + 1)))
        self.assertTrue(checker.check_yaml(WORKFLOW, "jobs: " + "[" * 2000 + "]" * 2000))

    def test_alias_expansion_is_not_exponential(self):
        text = "a0: &a0 [hello]\n"
        for i in range(1, 30):
            text += f"a{i}: &a{i} [*a{i-1}, *a{i-1}]\n"
        text += "jobs: {}\n"
        self.assertEqual([], checker.check_yaml(WORKFLOW, text))

    def test_annotation_escapes_workflow_commands(self):
        result = checker.annotation(checker.Finding("bad,\n::warning::%.yml", 3, "message"))
        self.assertNotIn("\n", result)
        self.assertIn("%2C%0A%3A%3Awarning", result)
        self.assertIn(checker.POLICY_URL, result)

    def test_local_scan_includes_untracked_and_handles_deleted_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "--quiet", temp], check=True)
            path = root / WORKFLOW
            path.parent.mkdir(parents=True)
            path.write_text(workflow("a/b@v1"), encoding="utf-8")
            self.assertEqual(1, len(checker.check_files(root)))
            subprocess.run(["git", "-C", temp, "add", WORKFLOW], check=True)
            path.unlink()
            self.assertEqual([], checker.check_files(root))
            path.write_bytes(b"\xff")
            self.assertIn("UTF-8", checker.check_files(root)[0].message)

    def test_local_read_errors_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(checker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, WORKFLOW + "\0")):
                with patch.object(Path, "read_text", side_effect=PermissionError("unreadable")), patch.object(Path, "stat") as stat:
                    stat.return_value.st_size = 10
                    self.assertIn("PermissionError", checker.check_files(root)[0].message)


class ReporterTests(unittest.TestCase):
    def setUp(self):
        self.pr = {"state": "open", "head": {"sha": SHA, "repo": {"full_name": "fork/project"}}}
        self.findings = [checker.Finding(WORKFLOW, 6, "Pin this action.")]
        self.existing = {
            "id": 123, "body": reporter.MARKER + "\nold",
            "user": {"login": "github-actions[bot]", "type": "Bot"},
        }

    def run_report(self, findings=None, existing=None, latest=None):
        with patch.object(reporter, "api") as api, patch.object(reporter, "scan_head") as scan, patch.object(reporter, "comments") as comments:
            api.side_effect = [self.pr, latest or self.pr, {}]
            scan.return_value = self.findings if findings is None else findings
            comments.return_value = existing or []
            reporter.report("base/project", 124, SHA)
            scan.assert_called_once_with("fork/project", SHA)
            return api.call_args_list

    def test_fork_violation_posts_one_base_issue_comment(self):
        calls = self.run_report()
        self.assertEqual(3, len(calls))
        self.assertEqual("repos/base/project/issues/124/comments", calls[-1].args[0])
        self.assertEqual("POST", calls[-1].args[2])
        self.assertIn(checker.POLICY_URL, calls[-1].args[1]["body"])

    def test_updates_existing_and_clears_after_fix(self):
        for findings in (self.findings, []):
            calls = self.run_report(findings, [self.existing])
            self.assertEqual("PATCH", calls[-1].args[2])
            self.assertEqual("repos/base/project/issues/comments/123", calls[-1].args[0])
        self.assertIn("violations resolved", calls[-1].args[1]["body"])

    def test_clean_pr_does_not_create_comment(self):
        self.assertEqual(2, len(self.run_report([])))

    def test_unchanged_comment_not_updated(self):
        self.existing["body"] = reporter.comment_body("fork/project", SHA, self.findings)
        self.assertEqual(2, len(self.run_report(existing=[self.existing])))

    def test_human_marker_not_overwritten(self):
        self.existing["user"] = {"login": "contributor", "type": "User"}
        self.assertEqual("POST", self.run_report(existing=[self.existing])[-1].args[2])

    def test_changed_head_during_scan_prevents_post(self):
        latest = copy.deepcopy(self.pr)
        latest["head"]["sha"] = "b" * 40
        self.assertEqual(2, len(self.run_report(latest=latest)))

    def test_superseded_or_closed_event_not_scanned(self):
        for state, sha in (("closed", SHA), ("open", "b" * 40)):
            self.pr["state"], self.pr["head"]["sha"] = state, sha
            with patch.object(reporter, "api", return_value=self.pr), patch.object(reporter, "scan_head") as scan:
                reporter.report("base/project", 124, SHA)
                scan.assert_not_called()

    def test_api_failure_does_not_publish_success(self):
        with patch.object(reporter, "api", return_value=self.pr) as api, patch.object(reporter, "scan_head", side_effect=RuntimeError("HTTP 403")):
            with self.assertRaisesRegex(RuntimeError, "403"):
                reporter.report("base/project", 124, SHA)
            self.assertEqual(1, api.call_count)

    def test_comment_pagination(self):
        with patch.object(reporter, "api", side_effect=[[{}] * 100, [self.existing]]) as api:
            self.assertEqual(101, len(reporter.comments("base/project", 124)))
            self.assertIn("page=2", api.call_args.args[0])

    def test_scan_uses_immutable_blobs(self):
        entry = {"path": WORKFLOW, "type": "blob", "mode": "100644", "size": 100, "sha": "blob-id"}
        blob = {"encoding": "base64", "content": base64.b64encode(workflow("a/b@v1").encode()).decode()}
        with patch.object(reporter, "api", side_effect=[{"tree": [entry], "truncated": False}, blob]) as api:
            self.assertEqual(1, len(reporter.scan_head("fork/project", SHA)))
            self.assertIn(f"/trees/{SHA}?", api.call_args_list[0].args[0])
            self.assertTrue(api.call_args.args[0].endswith("/blobs/blob-id"))

    def test_tree_truncation_is_error(self):
        with patch.object(reporter, "api", return_value={"truncated": True}):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                reporter.scan_head("fork/project", SHA)

    def test_oversized_and_symlink_blobs_not_fetched(self):
        for mode, size in (("120000", 100), ("100644", checker.MAX_FILE_BYTES + 1)):
            entry = {"path": WORKFLOW, "type": "blob", "mode": mode, "size": size, "sha": "blob-id"}
            with patch.object(reporter, "api", return_value={"tree": [entry]}) as api:
                self.assertEqual(1, len(reporter.scan_head("fork/project", SHA)))
                self.assertEqual(1, api.call_count)

    def test_comment_does_not_render_untrusted_paths_or_commands(self):
        findings = [checker.Finding(".github/workflows/<img>@all\n::error::.yml", 1, "Invalid ref.")]
        text = reporter.comment_body("fork/project", SHA, findings)
        self.assertNotIn("<img>", text)
        self.assertNotIn("@all", text)
        self.assertIn("%3Cimg%3E%40all%0A", text)
        self.assertLess(len(reporter.comment_body("fork/project", SHA, findings * 1000)), 65000)


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def read_workflow(self, name):
        return yaml.load((self.root / ".github" / "workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_required_check_is_unfiltered_and_read_only(self):
        data = self.read_workflow("skill-evals.yml")
        self.assertEqual({"branches": ["main"]}, data["on"]["pull_request"])
        self.assertEqual({"contents": "read"}, data["permissions"])
        job = data["jobs"]["static-checks"]
        self.assertEqual("Static skill checks", job["name"])
        runs = [step.get("run", "") for step in job["steps"]]
        self.assertIn("python .github/evals/check_action_pins.py", runs)
        self.assertTrue(any("test_action_pins.py" in run for run in runs))

    def test_privileged_reporter_executes_only_trusted_base(self):
        data = self.read_workflow("action-pins-pr-comment.yml")
        self.assertEqual(["pull_request_target"], list(data["on"]))
        steps = data["jobs"]["report"]["steps"]
        self.assertEqual("${{ github.event.pull_request.base.sha }}", steps[0]["with"]["ref"])
        self.assertEqual("false", steps[0]["with"]["persist-credentials"])
        self.assertEqual("python .github/evals/report_action_pins.py", steps[-1]["run"])
        self.assertEqual("${{ github.event.pull_request.head.sha }}", steps[-1]["env"]["PR_HEAD_SHA"])
        self.assertNotIn("${{", steps[-1]["run"])
        self.assertEqual({"contents": "read", "pull-requests": "write"}, data["jobs"]["report"]["permissions"])
        self.assertTrue(all("GH_TOKEN" not in step.get("env", {}) for step in steps[:-1]))

    def test_dependabot_titles_match_metadata_rule(self):
        data = yaml.safe_load((self.root / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
        self.assertEqual({"prefix": "ci"}, data["updates"][0]["commit-message"])
        self.assertEqual(7, data["updates"][0]["cooldown"]["default-days"])

    def test_codeql_uploads_fork_results_without_privileged_checkout(self):
        data = self.read_workflow("codeql.yml")
        self.assertEqual({"push", "pull_request", "schedule"}, set(data["on"]))
        self.assertEqual({"branches": ["main"]}, data["on"]["pull_request"])
        job = data["jobs"]["analyze"]
        self.assertEqual(
            {"actions": "read", "contents": "read", "security-events": "write"},
            job["permissions"],
        )
        checkout, init, analyze = job["steps"]
        self.assertEqual({"persist-credentials": "false"}, checkout["with"])
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertTrue(init["uses"].startswith("github/codeql-action/init@"))
        self.assertTrue(analyze["uses"].startswith("github/codeql-action/analyze@"))
        self.assertEqual(init["uses"].split("@")[1], analyze["uses"].split("@")[1])
        self.assertEqual("always", analyze["with"]["upload"])
        self.assertEqual("/language:python", analyze["with"]["category"])

    def test_contributor_policy_anchor_exists(self):
        text = (self.root / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("## GitHub Actions Pinning Policy", text)
        self.assertIn("check_action_pins.py", text)


if __name__ == "__main__":
    unittest.main()
