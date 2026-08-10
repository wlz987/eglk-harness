"""WA-Hard task 11: eval materialize → mock run → offline score (never Gate)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.eval.eval_runner import prepare_task_workdir, score_offline
from tests.conftest import default_eval_root

EVAL_ROOT = default_eval_root()
WA_PACK = EVAL_ROOT / "wa_hard" / "pack.json"
WA_PACK_EX = EVAL_ROOT / "wa_hard" / "pack.example.json"


@unittest.skipUnless(
    WA_PACK.is_file() or WA_PACK_EX.is_file(),
    reason="experiment/eval wa_hard pack not present",
)
class TestWa11MockPipeline(unittest.TestCase):
    def test_materialize_mock_run_and_score(self) -> None:
        os.environ["EGLK_EVAL_ROOT"] = str(EVAL_ROOT)
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            prepare_task_workdir(EVAL_ROOT, suite="wa_hard", task_id="11", out_dir=workdir)
            self.assertTrue((workdir / ".goal.md").is_file())

            result = asyncio.run(
                _run_loop(
                    RunRequest(
                        workdir=workdir,
                        agent="mock",
                        fake_mode="admit",
                        max_ticks=16,
                        compile="auto",
                    )
                )
            )
            self.assertEqual(result.get("stop_reason"), "terminal:succeeded")
            outcome = result.get("outcome") or {}
            self.assertTrue(outcome.get("ok"))

            scored = score_offline(
                suite="wa_hard",
                task_id="11",
                workdir=workdir,
                eval_root=EVAL_ROOT,
            )
            self.assertEqual(scored.suite, "wa_hard")
            self.assertTrue(scored.ok)


if __name__ == "__main__":
    unittest.main()
