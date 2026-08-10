"""weave_thin and scenarios eval connectors."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.eval.eval_runner import prepare_task_workdir, score_offline
from eglk_harness.domain.eval.loader import load_suite_module
from eglk_harness.domain.eval.suite_ops import list_task_rows

EVAL_ROOT = Path(os.environ.get("EGLK_EVAL_ROOT", "/home/wlz/alw/experiment/eval")).resolve()


class WeaveThinConnectorTests(unittest.TestCase):
    def test_list_tasks(self) -> None:
        mod = load_suite_module("weave_thin", EVAL_ROOT)
        rows = list_task_rows(mod, EVAL_ROOT)
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(rows[0]["id"], "toy-hello")

    def test_offline_score_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            prepare_task_workdir(EVAL_ROOT, suite="weave_thin", task_id="toy-hello", out_dir=workdir)
            (workdir / "hello.txt").write_text("hello from eglk\n", encoding="utf-8")
            result = score_offline(
                suite="weave_thin",
                task_id="toy-hello",
                workdir=workdir,
                eval_root=EVAL_ROOT,
            )
            self.assertTrue(result.ok)
            self.assertTrue(result.scores.get("contains_ok"))


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
