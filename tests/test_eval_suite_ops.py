"""Eval connector loads and suite_ops."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.eval.loader import load_suite_module
from eglk_harness.domain.eval.suite_ops import list_task_rows, score_task

EVAL_ROOT = Path(os.environ.get("EGLK_EVAL_ROOT", "/home/wlz/alw/experiment/eval")).resolve()


class EvalSuiteOpsTests(unittest.TestCase):
    def test_wa_hard_module(self) -> None:
        wa = load_suite_module("wa_hard", EVAL_ROOT)
        self.assertTrue(hasattr(wa, "load_pack_index"))
        self.assertTrue(hasattr(wa, "wa_hard_boundary"))

    def test_list_task_rows(self) -> None:
        mod = load_suite_module("wa_hard", EVAL_ROOT)
        rows = list_task_rows(mod, EVAL_ROOT)
        self.assertGreater(len(rows), 0)
        self.assertIn("id", rows[0])
        self.assertIn("summary", rows[0])

    def test_score_placeholder(self) -> None:
        mod = load_suite_module("wa_hard", EVAL_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            scores, ok, detail = score_task(
                mod,
                suite="wa_hard",
                task_id="1",
                workdir=workdir,
                eval_root=EVAL_ROOT,
            )
            self.assertTrue(ok)
            self.assertEqual(scores.get("task_id"), "1")
            self.assertIn(detail, ("recorded_only", "no_offline_scorer; recorded run only"))


if __name__ == "__main__":
    unittest.main()
