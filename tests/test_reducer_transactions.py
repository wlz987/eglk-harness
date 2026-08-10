"""Reducer transaction shadow map — prepared / committed / rolled_back."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.reducer import reduce_events


class TestReducerTransactionStates(unittest.TestCase):
    def test_transaction_lifecycle_in_projection(self) -> None:
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
            tx = {
                "transaction_id": "tx-1",
                "side_effect_class": "reversible",
                "actions": [],
            }
            h.transaction_prepared(tx)
            proj = h.projection()
            self.assertEqual(proj.transaction_states["tx-1"], "prepared")
            h.transaction_rolled_back("tx-1")
            proj = h.projection()
            self.assertEqual(proj.transaction_states["tx-1"], "rolled_back")

            h.transaction_prepared({"transaction_id": "tx-2", "side_effect_class": "reversible"})
            h._append(
                "TransactionCommitted",
                {"transaction_id": "tx-2", "world_revision": 1, "touches": []},
            )
            proj = h.projection()
            self.assertEqual(proj.transaction_states["tx-2"], "committed")

            h.transaction_prepared({"transaction_id": "tx-3", "side_effect_class": "reversible"})
            h.transaction_compensated("tx-3")
            proj = h.projection()
            self.assertEqual(proj.transaction_states["tx-3"], "compensated")

            replay = reduce_events(store.read_all())
            self.assertEqual(replay.transaction_states, proj.transaction_states)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
