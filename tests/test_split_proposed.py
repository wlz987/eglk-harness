"""SplitProposed event flow (symmetric to merge)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.advisors import build_mechanical_split_candidate
from eglk_harness.domain.kernel.command_handler import CommandHandler


class TestSplitProposed(unittest.TestCase):
    def test_propose_split_emits_only_proposed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
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
                    "title": "t",
                    "obligation_refs": ["ob-1"],
                    "obligations": [
                        {
                            "id": "ob-1",
                            "requirement_id": "req-1",
                            "statement": "hello.txt exists",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            mech = build_mechanical_split_candidate(h.projection(), "root", step=0)
            self.assertIsNotNone(mech)
            res = h.propose_split(mech)
            self.assertTrue(res.ok)
            types = [e.type for e in store.read_all()]
            self.assertIn("SplitProposed", types)
            self.assertNotIn("SplitCommitted", types)
            self.assertEqual(h.projection().nodes["root"].status, "ready")
            store.release_lease(holder="t")
            store.close()

    def test_commit_split_emits_proposed_and_committed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
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
                    "title": "t",
                    "obligation_refs": ["ob-1"],
                    "obligations": [
                        {
                            "id": "ob-1",
                            "requirement_id": "req-1",
                            "statement": "deliver hello.txt",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            h.node_ready("root")
            mech = build_mechanical_split_candidate(h.projection(), "root", step=0)
            self.assertIsNotNone(mech)
            res = h.commit_split(mech, actor="governor")
            self.assertTrue(res.ok, res.error)
            types = [e.type for e in store.read_all()]
            self.assertIn("SplitProposed", types)
            self.assertIn("SplitCommitted", types)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
