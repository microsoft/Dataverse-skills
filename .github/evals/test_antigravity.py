# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Regression tests for the Antigravity Marketplace package contract."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import static_checks


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = Path(".github/plugins/dataverse")


class AntigravityPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        paths = {
            Path("README.md"),
            Path("gemini-extension.json"),
            Path(".github/plugin/marketplace.json"),
            Path(".cursor-plugin/marketplace.json"),
            PLUGIN_ROOT / ".antigravity-plugin/plugin.json",
            PLUGIN_ROOT / "gemini-extension.json",
            PLUGIN_ROOT / "README.md",
            PLUGIN_ROOT / ".claude-plugin/plugin.json",
            PLUGIN_ROOT / ".github/plugin/plugin.json",
            PLUGIN_ROOT / ".cursor-plugin/plugin.json",
            PLUGIN_ROOT / ".codex-plugin/plugin.json",
            PLUGIN_ROOT / "assets/dataverse-logo.svg",
            PLUGIN_ROOT / "scripts/auth.py",
            PLUGIN_ROOT / "skills/dv-connect/SKILL.md",
            PLUGIN_ROOT / "skills/dv-connect/references/mcp-configuration.md",
        }
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / relative, target)
        self.manifest_path = self.root / PLUGIN_ROOT / ".antigravity-plugin/plugin.json"
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def check_manifest(self, manifest):
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return static_checks.check_antigravity_plugin(self.root)

    def test_complete_package_passes(self):
        self.assertEqual(self.check_manifest(self.manifest), [])
        self.assertEqual(static_checks.check_version_consistency(self.root), [])

    def test_required_marketplace_fields_cannot_be_removed(self):
        for field in self.manifest:
            with self.subTest(field=field):
                candidate = copy.deepcopy(self.manifest)
                del candidate[field]
                self.assertTrue(self.check_manifest(candidate))

    def test_invalid_manifest_root_and_unknown_fields_fail(self):
        self.assertTrue(self.check_manifest([]))
        self.assertTrue(self.check_manifest({**self.manifest, "unknown": True}))

    def test_listing_description_is_independent_of_other_hosts(self):
        candidate = {**self.manifest, "description": "Explore Microsoft Dataverse data."}
        self.assertEqual(self.check_manifest(candidate), [])
        self.assertEqual(static_checks.check_description_consistency(self.root), [])

    def test_invalid_description_fails(self):
        for description in (None, "", " ", "x" * 161, "x" * 160 + " ", 42):
            with self.subTest(description=description):
                self.assertTrue(self.check_manifest({**self.manifest, "description": description}))

    def test_invalid_starter_prompts_fail(self):
        for prompts in (None, [], [""], [" "], [42], ["prompt"] * 4, "prompt"):
            with self.subTest(prompts=prompts):
                self.assertTrue(self.check_manifest({**self.manifest, "suggestedPrompts": prompts}))

    def test_invalid_keywords_fail(self):
        for keywords in (None, [], [""], ["Dataverse"], [42], "dataverse"):
            with self.subTest(keywords=keywords):
                self.assertTrue(self.check_manifest({**self.manifest, "keywords": keywords}))

    def test_version_drift_fails(self):
        self.assertTrue(self.check_manifest({**self.manifest, "version": "0.0.0"}))
        self.assertTrue(any("version mismatch" in issue for issue in static_checks.check_version_consistency(self.root)))

    def test_preinstall_readme_is_required(self):
        (self.root / PLUGIN_ROOT / "README.md").unlink()
        self.assertTrue(any("EVAL-ANTIGRAVITY-05" in issue for issue in self.check_manifest(self.manifest)))

    def test_missing_logo_is_rejected(self):
        (self.root / PLUGIN_ROOT / "assets/dataverse-logo.svg").unlink()
        self.assertTrue(any("EVAL-ANTIGRAVITY-06" in issue for issue in self.check_manifest(self.manifest)))
        self.assertTrue(any(".antigravity-plugin/plugin.json" in issue for issue in static_checks.check_manifest_assets(self.root)))

    def test_invalid_logo_shapes_are_rejected(self):
        logo_path = self.root / PLUGIN_ROOT / "assets/dataverse-logo.svg"
        for logo in (
            '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="256" viewBox="0 0 128 256"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 96"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 -1 -1"/>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="NaN" height="NaN" viewBox="0 0 128 128"/>',
            '<svg/>',
            '<svg',
        ):
            with self.subTest(logo=logo):
                logo_path.write_text(logo, encoding="utf-8")
                self.assertTrue(any("EVAL-ANTIGRAVITY-06" in issue for issue in self.check_manifest(self.manifest)))


if __name__ == "__main__":
    unittest.main()