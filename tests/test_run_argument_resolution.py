from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from framework.cli.main import DEFAULT_RUNS_DIRECTORY, build_parser

RUN_ID = "20260719T161514709224Z"
RUN_SUBCOMMANDS = ("policy", "run", "compare", "report")


class RunArgumentResolutionTests(unittest.TestCase):
    """--run accepts a run directory path or a bare run ID.

    Regression guard: the CLI previously required a path, so a bare run ID
    failed even when the run existed under artifacts/runs.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.runs_directory = self.root / DEFAULT_RUNS_DIRECTORY
        self.run_directory = self.runs_directory / RUN_ID
        self.run_directory.mkdir(parents=True)

        origin = Path.cwd()
        self.addCleanup(os.chdir, origin)
        os.chdir(self.root)

        self.parser = build_parser()

    def parse_run(self, value: str, command: str = "compare") -> Path:
        return self.parser.parse_args([command, "--run", value]).run

    def test_bare_run_id_resolves_under_runs_directory(self) -> None:
        self.assertTrue(self.parse_run(RUN_ID).is_dir())

    def test_bare_run_id_resolves_for_every_run_subcommand(self) -> None:
        for command in RUN_SUBCOMMANDS:
            with self.subTest(command=command):
                self.assertTrue(self.parse_run(RUN_ID, command).is_dir())

    def test_explicit_path_is_preserved(self) -> None:
        relative = f"{DEFAULT_RUNS_DIRECTORY.as_posix()}/{RUN_ID}"
        self.assertEqual(self.parse_run(relative), Path(relative))

    def test_run_directory_relative_to_working_directory(self) -> None:
        os.chdir(self.runs_directory)
        for value in (RUN_ID, f"./{RUN_ID}"):
            with self.subTest(value=value):
                self.assertTrue(self.parse_run(value).is_dir())

    def test_unresolvable_value_is_returned_unchanged(self) -> None:
        # Downstream reporting owns the "Run directory does not exist" error,
        # so resolution must not raise or rewrite the value here.
        self.assertEqual(self.parse_run("not-a-run"), Path("not-a-run"))

    def test_nested_path_is_not_treated_as_run_id(self) -> None:
        nested = f"somewhere/else/{RUN_ID}"
        self.assertEqual(self.parse_run(nested), Path(nested))


if __name__ == "__main__":
    unittest.main()
