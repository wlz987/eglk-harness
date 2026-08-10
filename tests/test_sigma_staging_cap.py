"""SIGMA_STAGING_MAX enforcement on sigma/refined/."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.product.init_project import init_project


class TestSigmaStagingCap(unittest.TestCase):
    def test_enforce_staging_cap_archives_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir)
            loop = paths.loop_goal_dir(workdir, "g1")
            refined = loop / "sigma" / "refined"
            refined.mkdir(parents=True)
            for i in range(55):
                (refined / f"{i:03d}.json").write_text(
                    json.dumps({"id": f"hit-{i}", "kind": "hit", "text": f"lesson {i}"}),
                    encoding="utf-8",
                )
            n = sigma.enforce_staging_cap(loop, max_items=50)
            self.assertEqual(5, n)
            remaining = sigma.list_refined(loop)
            self.assertLessEqual(len(remaining), 51)
            self.assertTrue(any(p.name.startswith("archive_") for p in remaining))

    def test_stage_tick_lesson_triggers_cap(self) -> None:
        from eglk_harness.domain.memory.refiner_batch import stage_tick_lesson

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir)
            loop = paths.loop_goal_dir(workdir, "g2")
            refined = loop / "sigma" / "refined"
            refined.mkdir(parents=True)
            for i in range(52):
                (refined / f"{i:03d}.json").write_text(
                    json.dumps({"id": f"hit-{i}", "text": "x"}),
                    encoding="utf-8",
                )
            stage_tick_lesson(
                loop,
                tick=99,
                decision={"decision": "repair", "reason": "incomplete", "subgoal_id": "root"},
            )
            self.assertLessEqual(len(sigma.list_refined(loop)), 51)


if __name__ == "__main__":
    unittest.main()
