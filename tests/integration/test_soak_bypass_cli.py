"""soak-bypass CLI with mock agent — all bypass roles without live LLM."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestSoakBypassCli(unittest.TestCase):
    def test_soak_bypass_mock_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "soak"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "eglk_harness.cli",
                    "soak-bypass",
                    "--workdir",
                    str(workdir),
                    "--agent",
                    "mock",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
            report_path = workdir / ".eglk-harness" / "soak" / "bypass" / "report.json"
            self.assertTrue(report_path.is_file())
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(data.get("ok"))
            roles = data.get("roles") or []
            self.assertGreaterEqual(len(roles), 4)


if __name__ == "__main__":
    unittest.main()
