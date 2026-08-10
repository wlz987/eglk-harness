"""Σ merge suggestions from ProjectionState (no legacy TaskTree)."""

from __future__ import annotations

import unittest

from eglk_harness.domain.kernel.reducer import NodeState, ProjectionState
from eglk_harness.domain.kernel.projection_view import iter_sibling_leaf_groups
from eglk_harness.domain.memory.sigma_merge import suggest_sibling_merges


def _two_leaf_state() -> ProjectionState:
    state = ProjectionState(root_id="root", run_status="running")
    state.nodes = {
        "root": NodeState(
            id="root",
            title="root",
            status="split",
            children=["a", "b"],
            depth=0,
        ),
        "a": NodeState(
            id="a",
            title="leaf a",
            status="ready",
            parent_id="root",
            obligation_refs=["ob-a"],
            depth=1,
        ),
        "b": NodeState(
            id="b",
            title="leaf b",
            status="ready",
            parent_id="root",
            obligation_refs=["ob-b"],
            depth=1,
        ),
    }
    state.obligations = {
        "ob-a": __import__(
            "eglk_harness.domain.kernel.reducer", fromlist=["ObligationState"]
        ).ObligationState(id="ob-a", statement="hello.txt exists"),
        "ob-b": __import__(
            "eglk_harness.domain.kernel.reducer", fromlist=["ObligationState"]
        ).ObligationState(id="ob-b", statement="hello.txt exists"),
    }
    return state


class SigmaMergeProjectionTests(unittest.TestCase):
    def test_iter_sibling_leaf_groups(self) -> None:
        groups = iter_sibling_leaf_groups(_two_leaf_state())
        self.assertEqual(len(groups), 1)
        parent_id, leaves = groups[0]
        self.assertEqual(parent_id, "root")
        self.assertEqual({x.id for x in leaves}, {"a", "b"})

    def test_suggest_on_criteria_overlap(self) -> None:
        state = _two_leaf_state()
        suggestions = suggest_sibling_merges(state, [], min_sim=0.45)
        self.assertTrue(suggestions)
        self.assertEqual(suggestions[0]["parent_id"], "root")
        self.assertIn("a", suggestions[0]["nodes"])
        self.assertIn("b", suggestions[0]["nodes"])


if __name__ == "__main__":
    unittest.main()
