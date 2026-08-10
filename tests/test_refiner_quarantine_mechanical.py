"""Refiner quarantine mechanical review (no LLM)."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.memory.lifecycle import quarantine_candidates, write_candidate
from eglk_harness.domain.memory.refiner_quarantine import llm_review_quarantined
from eglk_harness.domain.product.init_project import init_project


class TestRefinerQuarantineMechanical(unittest.TestCase):
    def test_low_conf_deprecated_mechanical(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="test",
                wrong="w",
                correct="lesson",
                conf=0.2,
                namespace="g1",
                origin_goal_id="g1",
                origin_run_id="run-g1-seq1",
            )
            rid = str(rec["id"])
            quarantine_candidates(workdir)
            stats = asyncio.run(
                llm_review_quarantined(
                    None,
                    workdir,
                    goal_id="g1",
                    origin_run_id="run-g1-seq2",
                )
            )
            self.assertGreaterEqual(stats["reviewed"], 1)
            from eglk_harness.domain.kernel import paths

            dep = paths.memory_lifecycle_dirs(workdir)["deprecated"]
            self.assertTrue((dep / f"{rid}.json").is_file())

    def test_high_conf_bumped_mechanical(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            rec = write_candidate(
                workdir,
                kind="sigma",
                cond="test",
                wrong="w",
                correct="lesson",
                conf=0.85,
                namespace="g1",
                origin_goal_id="g1",
                origin_run_id="run-g1-seq1",
            )
            rid = str(rec["id"])
            quarantine_candidates(workdir)
            stats = asyncio.run(
                llm_review_quarantined(
                    None,
                    workdir,
                    goal_id="g1",
                    origin_run_id="run-g1-seq2",
                )
            )
            self.assertGreaterEqual(stats["verification_bumps"], 1)
            from eglk_harness.domain.kernel import paths

            quar = paths.memory_lifecycle_dirs(workdir)["quarantined"]
            data = json.loads((quar / f"{rid}.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(int(data.get("verifications") or 0), 1)


if __name__ == "__main__":
    unittest.main()
