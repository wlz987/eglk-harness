"""Advisor trigger table — CANDIDATES_MAX and SWARM_BUDGET_FLOOR."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.advisors import run_candidate_selector
from eglk_harness.domain.kernel.reducer import ProjectionState
from eglk_harness.domain.kernel.scheduler import advisor_plan
from eglk_harness.domain.kernel.swarm import decide_swarm


class TestAdvisorTriggers(unittest.TestCase):
    def test_candidates_max_forces_selector(self) -> None:
        state = ProjectionState(cognitive_tokens=0, cognitive_tokens_max=1000)
        plan = advisor_plan(state, candidates_count=P.CANDIDATES_MAX + 1)
        self.assertTrue(plan["candidate_selector"])
        swarm = decide_swarm(candidate_count=P.CANDIDATES_MAX + 1)
        self.assertTrue(swarm.candidate_selector)
        self.assertIn("candidates_overflow", swarm.reasons)

    def test_budget_floor_disables_explorer(self) -> None:
        state = ProjectionState(
            cognitive_tokens=int(P.COGNITIVE_TOKENS_MAX * 0.95),
            cognitive_tokens_max=P.COGNITIVE_TOKENS_MAX,
        )
        plan = advisor_plan(state, candidates_count=0)
        self.assertFalse(plan["explorer"])
        swarm = decide_swarm(
            cognitive_tokens=state.cognitive_tokens,
            cognitive_tokens_max=state.cognitive_tokens_max,
        )
        self.assertFalse(swarm.explorer)
        self.assertIn("budget_floor", swarm.reasons)

    def test_candidate_selector_prunes_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            cand = loop / "candidates"
            cand.mkdir()
            for i in range(P.CANDIDATES_MAX + 5):
                (cand / f"explorer_{i:03d}.json").write_text(
                    f'{{"role":"explorer","score":{i}}}\n',
                    encoding="utf-8",
                )
            result = run_candidate_selector(loop, keep_max=P.CANDIDATES_MAX)
            self.assertTrue(result["forced"])
            self.assertEqual(P.CANDIDATES_MAX, result["kept"])
            self.assertEqual(5, result["pruned"])


if __name__ == "__main__":
    unittest.main()
