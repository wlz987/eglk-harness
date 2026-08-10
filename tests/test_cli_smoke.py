"""CLI smoke — subcommands import without running live agents."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eglk_harness.cli import main as cli_main
from eglk_harness.domain.product.check_projections import check_projections
from eglk_harness.domain.product.init_project import init_project


class CliSmokeTests(unittest.TestCase):
    def test_check_projections_ok(self) -> None:
        report = check_projections()
        self.assertTrue(report.ok, report.to_dict())

    def test_cli_module_importable(self) -> None:
        self.assertTrue(callable(cli_main))

    def test_cli_check_projections_subprocess(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "eglk_harness.cli", "check-projections"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_cli_doctor_json_subprocess(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "eglk_harness.cli", "doctor", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_cli_replay_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            (workdir / ".goal.md").write_text(
                "# Replay\n\n## Done criteria\n- hello.txt exists\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "eglk_harness.cli",
                    "replay",
                    "--workdir",
                    str(workdir),
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            data = json.loads(proc.stdout)
            self.assertIn("run", data)

    def test_cli_plugin_list_subprocess(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "eglk_harness.cli", "plugin", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("plugin", proc.stdout.lower())

    def test_cli_soak_bypass_mock_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "eglk_harness.cli",
                    "soak-bypass",
                    "--workdir",
                    td,
                    "--agent",
                    "mock",
                    "--timeout",
                    "30",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            report_path = Path(td) / ".eglk-harness" / "soak" / "bypass" / "report.json"
            self.assertTrue(report_path.is_file())


if __name__ == "__main__":
    unittest.main()
