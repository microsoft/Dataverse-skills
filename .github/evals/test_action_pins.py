"""Valid `uses:` forms must pass and mutable refs must fail, so the required check never blocks a correct pin."""
import pathlib
import tempfile
import unittest

import check_action_pins as checker

SHA, DIGEST = "a" * 40, "b" * 64
VALID = [f"actions/checkout@{SHA}", f"o/r/sub/dir@{SHA}", f"o/r/.github/workflows/w.yml@{SHA}", "./",
         "./.github/actions/local", "./.github/workflows/local.yml", f"docker://ghcr.io/o/i:1@sha256:{DIGEST}"]
INVALID = ["actions/checkout@v4", "o/r@main", "o/r@abc1234", f"o/r@{SHA[:-1]}", "o/r@${{ env.REF }}",
           "./../escape", f"o/../r@{SHA}", "docker://alpine:3", "null", "[]"]


class PinCheckTests(unittest.TestCase):
    def scan(self, text):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp, "w.yml")
            path.write_text(text, encoding="utf-8")
            return checker.check(path, "w.yml")

    def test_step_and_reusable_workflow_refs(self):
        for ref, findings in [(r, 0) for r in VALID] + [(r, 2) for r in INVALID]:
            with self.subTest(ref=ref):
                self.assertEqual(findings, len(self.scan(f"jobs:\n  a:\n    steps:\n      - uses: {ref}\n  b:\n    uses: {ref}\n")))

    def test_yaml_shapes(self):
        self.assertEqual(1, len(self.scan("jobs:\n  a:\n    steps: &s\n      - uses: o/r@v1\n  b:\n    steps: *s\n")))
        self.assertEqual(1, len(self.scan(f"jobs:\n  a:\n    steps:\n      - uses: o/r@{SHA}\n        uses: o/r@v1\n")))
        self.assertEqual([], self.scan("name: not a workflow\n"))
        self.assertIn("Invalid YAML", self.scan("jobs: [")[0][2])


if __name__ == "__main__":
    unittest.main()
