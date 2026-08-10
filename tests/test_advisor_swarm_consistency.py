"""advisor_plan and decide_swarm trigger alignment."""

from __future__ import annotations

import unittest

from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.reducer import ProjectionState
from eglk_harness.domain.kernel.scheduler import advisor_plan
from eglk_harness.domain.kernel.swarm import decide_swarm


class TestAdvisorSwarmConsistency(unittest.TestCase):
    def test_budget_floor_both_disable_explorer(self) -> None:
        state = ProjectionState(
            cognitive_tokens=int(P.COGNITIVE_TOKENS_MAX * 0.96),
            cognitive_tokens_max=P.COGNITIVE_TOKENS_MAX,
        )
        plan = advisor_plan(state, candidates_count=0)
        swarm = decide_swarm(
            cognitive_tokens=state.cognitive_tokens,
            cognitive_tokens_max=state.cognitive_tokens_max,
        )
        self.assertFalse(plan["explorer"])
        self.assertFalse(swarm.explorer)

    def test_candidates_overflow_both_force_selector(self) -> None:
        state = ProjectionState(cognitive_tokens=0, cognitive_tokens_max=1000)
        overflow = P.CANDIDATES_MAX + 3
        plan = advisor_plan(state, candidates_count=overflow)
        swarm = decide_swarm(candidate_count=overflow, cognitive_tokens=0, cognitive_tokens_max=1000)
        self.assertTrue(plan["candidate_selector"])
        self.assertTrue(swarm.candidate_selector)

    def test_soft_zero_disables_swarm_roles(self) -> None:
        state = ProjectionState(cognitive_tokens=0, cognitive_tokens_max=1000)
        plan = advisor_plan(state, candidates_count=0, swarm_soft="0")
        swarm = decide_swarm(soft="0")
        self.assertFalse(plan["explorer"])
        self.assertFalse(swarm.explorer)
        self.assertFalse(swarm.verifier)
        self.assertFalse(swarm.candidate_selector)


if __name__ == "__main__":
    unittest.main()
