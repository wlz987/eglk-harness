"""Mechanical Claim recovery when Maker worker fails but boundary is satisfied."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.kernel.run_loop import _recoverable_worker_error


class MechanicalRecoveryTests(unittest.TestCase):
    def test_recoverable_worker_errors(self) -> None:
        self.assertTrue(_recoverable_worker_error("maker_failed"))
        self.assertTrue(_recoverable_worker_error("maker_claim_episode_failed"))
        self.assertFalse(_recoverable_worker_error("abort:cognitive_tokens_max"))

    def test_synthesize_after_boundary_ok(self) -> None:
        from eglk_harness.domain.runtime.mechanical_claim import synthesize_mechanical_claim

        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "done.txt").write_text("ok\n", encoding="utf-8")
            claim = synthesize_mechanical_claim(
                workdir=workdir,
                title="t",
                subgoal_id="root",
                contract_ref="wc-x",
                world_revision=0,
                obligation_refs=["ob-1"],
                boundary=["MUST_EXIST: done.txt"],
                tick=0,
            )
            self.assertIsNotNone(claim)


if __name__ == "__main__":
    unittest.main()
