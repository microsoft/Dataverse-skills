# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Tests for the Gemini CLI compatibility projection."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sync_gemini_projection


class GeminiProjectionTests(unittest.TestCase):
    def test_sync_creates_exact_projection_and_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "canonical"
            target = root / "projection"
            (source / "nested").mkdir(parents=True)
            target.mkdir()
            (source / "nested" / "content.md").write_text("current\n", encoding="utf-8")
            (target / "stale.md").write_text("stale\n", encoding="utf-8")

            with mock.patch.object(
                sync_gemini_projection, "PROJECTIONS", {source: target}
            ):
                sync_gemini_projection.sync_projection()
                self.assertEqual([], sync_gemini_projection.check_projection())

            self.assertFalse((target / "stale.md").exists())
            self.assertEqual(
                "current\n",
                (target / "nested" / "content.md").read_text(encoding="utf-8"),
            )

    def test_check_reports_missing_changed_and_extra_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "canonical"
            target = root / "projection"
            source.mkdir()
            target.mkdir()
            (source / "missing.md").write_text("missing\n", encoding="utf-8")
            (source / "changed.md").write_text("expected\n", encoding="utf-8")
            (target / "changed.md").write_text("different\n", encoding="utf-8")
            (target / "extra.md").write_text("extra\n", encoding="utf-8")

            with mock.patch.object(
                sync_gemini_projection, "PROJECTIONS", {source: target}
            ):
                differences = sync_gemini_projection.check_projection()

            self.assertEqual(
                [
                    "missing: projection/missing.md",
                    "extra: projection/extra.md",
                    "changed: projection/changed.md",
                ],
                differences,
            )

    def test_projection_ignores_python_cache_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "canonical"
            target = root / "projection"
            (source / "__pycache__").mkdir(parents=True)
            target.mkdir()
            (source / "__pycache__" / "module.pyc").write_bytes(b"cache")

            self.assertEqual(
                [], sync_gemini_projection._projection_differences(source, target)
            )

    def test_check_rejects_missing_canonical_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "missing-canonical"
            target = root / "projection"

            with mock.patch.object(
                sync_gemini_projection, "PROJECTIONS", {source: target}
            ):
                differences = sync_gemini_projection.check_projection()

            self.assertEqual([f"canonical source missing: {source}"], differences)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are not supported")
    def test_check_rejects_nested_source_symlink(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "canonical"
            target = root / "projection"
            source.mkdir()
            target.mkdir()
            real_file = root / "outside.md"
            real_file.write_text("outside\n", encoding="utf-8")
            try:
                os.symlink(real_file, source / "linked.md")
            except OSError as error:
                self.skipTest(f"symlink creation is unavailable: {error}")

            with mock.patch.object(
                sync_gemini_projection, "PROJECTIONS", {source: target}
            ):
                differences = sync_gemini_projection.check_projection()

            self.assertEqual(
                ["canonical symlink not allowed: canonical/linked.md"], differences
            )


if __name__ == "__main__":
    unittest.main()
