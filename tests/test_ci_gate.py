"""CI script smoke — verify gate components (does not recurse into scripts/ci.sh)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_SH = ROOT / "scripts" / "ci.sh"


class TestCiGate(unittest.TestCase):
    def test_ci_script_exists(self) -> None:
        self.assertTrue(CI_SH.is_file())

    def test_check_projections_and_pytest_pass(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "eglk_harness.domain.product.check_projections"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-q",
                "--tb=short",
                "--ignore=tests/test_ci_gate.py",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:] if proc.stderr else proc.stdout[-3000:])


if __name__ == "__main__":
    unittest.main()
