"""eval_runner uses dynamic suite connectors for pack suites."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.eval.eval_runner import prepare_task_workdir, score_offline

from tests.conftest import default_eval_root

EVAL_ROOT = default_eval_root()


class EvalRunnerPackSuiteTests(unittest.TestCase):
    def test_prepare_wa_hard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            prepare_task_workdir(EVAL_ROOT, suite="wa_hard", task_id="11", out_dir=out)
            self.assertTrue((out / ".goal.md").is_file())
            canonical = out / ".eglk-harness" / "deliverable_hint.json"
            self.assertTrue(canonical.is_file())
            self.assertFalse((out / ".wa_hard_agent_response_hint.json").is_file())

    def test_score_wa_hard_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            result = score_offline(
                suite="wa_hard",
                task_id="11",
                workdir=workdir,
                eval_root=EVAL_ROOT,
            )
            self.assertEqual(result.suite, "wa_hard")
            self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
