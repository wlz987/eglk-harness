"""Scenarios eval connector tests (maturity index; never Gate)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.eval.eval_runner import prepare_task_workdir
from eglk_harness.domain.eval.loader import load_suite_module
from eglk_harness.domain.eval.suite_ops import list_task_rows

EVAL_ROOT = Path(os.environ.get("EGLK_EVAL_ROOT", "/home/wlz/alw/experiment/eval")).resolve()


class ScenariosConnectorTests(unittest.TestCase):
    def test_list_tasks(self) -> None:
        mod = load_suite_module("scenarios", EVAL_ROOT)
        rows = list_task_rows(mod, EVAL_ROOT)
        self.assertGreater(len(rows), 0)
        self.assertIn("toy_hello3", {r["id"] for r in rows})

    def test_materialize_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            prepare_task_workdir(EVAL_ROOT, suite="scenarios", task_id="toy_hello3", out_dir=out)
            text = (out / ".goal.md").read_text(encoding="utf-8")
            self.assertIn("toy_hello3", text)


if __name__ == "__main__":
    unittest.main()
