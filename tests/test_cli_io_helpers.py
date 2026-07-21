"""T5-1: the consolidated atomic-write primitive and robust JSONL reader.

These lock in the single-point fixes that replaced the scattered copies: a
unique temp name + fsync for durable atomic writes, and a reader that raises a
clear contextual error instead of a raw JSONDecodeError crash.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from framework.cli.main import (
    _atomic_write_bytes,
    _read_cli_jsonl,
    _write_jsonl_atomic,
    write_manifest_atomic,
)


class AtomicWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def test_writes_content_and_leaves_no_temp_debris(self) -> None:
        target = self.root / "manifest.json"
        _atomic_write_bytes(target, b'{"a": 1}')
        self.assertEqual(target.read_bytes(), b'{"a": 1}')
        # os.replace moves the unique temp onto the target, so nothing lingers.
        self.assertEqual([p.name for p in self.root.iterdir()], ["manifest.json"])

    def test_overwrites_existing_file(self) -> None:
        target = self.root / "rows.jsonl"
        target.write_text("stale contents")
        _write_jsonl_atomic(target, [{"x": 1}, {"y": 2}])
        self.assertEqual(target.read_text(), '{"x": 1}\n{"y": 2}\n')
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_failure_preserves_original_and_cleans_temp(self) -> None:
        target = self.root / "manifest.json"
        target.write_bytes(b"original")
        # Fail at the rename, after the temp file has been created and written.
        with mock.patch(
            "framework.cli.main.os.replace", side_effect=OSError("boom")
        ):
            with self.assertRaises(OSError):
                _atomic_write_bytes(target, b"replacement")
        # The original is untouched and the temp file was cleaned up.
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual([p.name for p in self.root.iterdir()], ["manifest.json"])

    def test_write_manifest_atomic_roundtrips(self) -> None:
        target = self.root / "manifest.json"
        write_manifest_atomic(target, {"run_id": "r", "count": 3})
        self.assertEqual(
            json.loads(target.read_text()), {"run_id": "r", "count": 3}
        )


class ReadCliJsonlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "rows.jsonl"

    def test_reads_dicts_and_skips_blanks_and_non_objects(self) -> None:
        self.path.write_text('{"a": 1}\n\n5\n"text"\n{"b": 2}\n')
        self.assertEqual(_read_cli_jsonl(self.path), [{"a": 1}, {"b": 2}])

    def test_malformed_line_raises_clear_error_with_file_and_line(self) -> None:
        # The inline reader this replaced raised a bare JSONDecodeError with no
        # artifact context; a torn line here would have crashed a CLI summary.
        self.path.write_text('{"a": 1}\n{not json\n')
        with self.assertRaises(ValueError) as context:
            _read_cli_jsonl(self.path)
        message = str(context.exception)
        self.assertIn("rows.jsonl", message)
        self.assertIn("line 2", message)


if __name__ == "__main__":
    unittest.main()
