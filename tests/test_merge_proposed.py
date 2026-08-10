"""MergeProposed event flow and mechanical merge candidate builder."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.advisors import build_mechanical_merge_candidate
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.scheduler import pick_sibling_merge_pair, should_propose_merge


def _bootstrap_two_leaf_goal(h: CommandHandler) -> tuple[str, str]:
    obligations = [
        {
            "id": "ob-1",
            "requirement_id": "req-1",
            "statement": "hello.txt exists",
            "verification_type": "custom_attestation",
            "status": "open",
            "origin": "root",
        },
        {
            "id": "ob-2",
            "requirement_id": "req-2",
            "statement": "hello.txt exists",
            "verification_type": "custom_attestation",
            "status": "open",
            "origin": "root",
        },
    ]
    h.run_created(
        goal_id="g",
        memory_digest="sha256:" + "a" * 64,
        cognitive_tokens_max=1000,
        repairs_max=8,
    )
    h.goal_compiled(
        {
            "source_digest": "sha256:" + "b" * 64,
            "root_node_id": "root",
            "title": "merge goal",
            "obligation_refs": ["ob-1", "ob-2"],
            "obligations": obligations,
        }
    )
    h.node_ready("root")
    split = h.commit_split(
        {
            "split_node": "root",
            "children": [
                {"id": "root.01", "title": "a", "obligation_refs": ["ob-1"], "depth": 1},
                {"id": "root.02", "title": "b", "obligation_refs": ["ob-2"], "depth": 1},
            ],
            "coverage_proof": {
                "parent_obligation_ids": ["ob-1", "ob-2"],
                "child_obligation_map": {"root.01": ["ob-1"], "root.02": ["ob-2"]},
                "proof_kind": "partition",
            },
        }
    )
    assert split.ok, split.error
    h.node_ready("root.01")
    h.node_ready("root.02")
    return "root.01", "root.02"


class TestMergeProposed(unittest.TestCase):
    def test_propose_merge_emits_only_proposed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf_goal(h)
            res = h.propose_merge(
                {
                    "into": "root.m001",
                    "node_ids": ["root.01", "root.02"],
                    "parent_id": "root",
                    "title": "merged",
                    "obligation_refs": ["ob-1", "ob-2"],
                }
            )
            self.assertTrue(res.ok)
            types = [e.type for e in store.read_all()]
            self.assertIn("MergeProposed", types)
            self.assertNotIn("MergeCommitted", types)
            self.assertEqual(h.projection().nodes["root.01"].status, "ready")
            store.release_lease(holder="t")
            store.close()

    def test_mechanical_candidate_on_criteria_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf_goal(h)
            proj = h.projection()
            self.assertTrue(should_propose_merge(proj))
            pair = pick_sibling_merge_pair(proj)
            self.assertIsNotNone(pair)
            mech = build_mechanical_merge_candidate(proj, step=1)
            self.assertIsNotNone(mech)
            self.assertEqual(mech["node_ids"], ["root.01", "root.02"])
            self.assertEqual(sorted(mech["obligation_refs"]), ["ob-1", "ob-2"])
            store.release_lease(holder="t")
            store.close()

    def test_commit_merge_rejects_non_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf_goal(h)
            res = h.commit_merge(
                {
                    "into": "root.m002",
                    "node_ids": ["root", "root.01"],
                    "parent_id": "root",
                    "obligation_refs": ["ob-1", "ob-2"],
                }
            )
            self.assertFalse(res.ok)
            self.assertTrue(res.rejected)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
