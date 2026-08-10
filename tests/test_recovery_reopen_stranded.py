"""Dangling TX recovery must reopen stranded in_progress nodes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.recovery import reconcile_dangling_transactions
from eglk_harness.domain.kernel.scheduler import select_ready_node


class RecoveryReopenTests(unittest.TestCase):
    def test_reopen_after_dangling_tx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.db")
            store.acquire_lease(holder="t")
            handler = CommandHandler(store)
            handler.run_created(
                goal_id="g-test",
                memory_digest="sha256:" + "a" * 64,
                cognitive_tokens_max=1000,
                repairs_max=8,
            )
            handler.goal_compiled(
                {
                    "source_digest": "sha256:" + "b" * 64,
                    "root_node_id": "root",
                    "title": "t",
                    "obligation_refs": ["ob-1"],
                    "obligations": [
                        {
                            "id": "ob-1",
                            "requirement_id": "req-1",
                            "statement": "s",
                            "verification_type": "custom_attestation",
                            "status": "open",
                            "origin": "root",
                        }
                    ],
                }
            )
            handler.node_ready("root")
            handler.contract_assembled(
                {
                    "schema": "eglk.work_contract",
                    "contract_id": "wc-1",
                    "node_id": "root",
                    "world_revision_base": 0,
                    "obligation_refs": ["ob-1"],
                    "dependencies": [],
                    "boundary": {"allowed_scope": ["workdir/**"], "forbidden_actions": []},
                    "capabilities": [],
                    "transaction_policy": {"side_effect_class_ceiling": ["read_only"]},
                    "cognitive_tokens_soft": 4000,
                    "prior_evidence_refs": [],
                }
            )
            handler.transaction_prepared(
                {
                    "schema": "eglk.world_transaction",
                    "transaction_id": "tx-1",
                    "node_id": "root",
                    "base_revision": 0,
                    "candidate_revision": None,
                    "side_effect_class": "read_only",
                    "action_intents": [],
                    "status": "prepared",
                    "idempotency_keys": [],
                    "compensation_ref": None,
                }
            )
            self.assertIsNone(select_ready_node(handler.projection()))
            self.assertEqual(handler.projection().nodes["root"].status, "in_progress")
            out = reconcile_dangling_transactions(handler)
            self.assertTrue(out["recovered"])
            self.assertEqual(out.get("reopened_nodes"), ["root"])
            self.assertEqual(handler.projection().nodes["root"].status, "ready")
            self.assertEqual(select_ready_node(handler.projection()), "root")
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
