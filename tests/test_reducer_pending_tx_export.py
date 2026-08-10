"""run_projection exports pending_transactions from transaction_states."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.reducer import run_projection_dict


class TestPendingTxExport(unittest.TestCase):
    def test_prepared_tx_listed_in_run_projection(self) -> None:
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
            h.transaction_prepared({"transaction_id": "tx-pending", "side_effect_class": "reversible"})
            h.transaction_prepared({"transaction_id": "tx-done", "side_effect_class": "reversible"})
            h._append(
                "TransactionCommitted",
                {"transaction_id": "tx-done", "world_revision": 1, "touches": []},
            )
            rp = run_projection_dict(h.projection())
            self.assertIn("tx-pending", rp.get("pending_transactions") or [])
            self.assertNotIn("tx-done", rp.get("pending_transactions") or [])
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
