"""CommandRejected is diagnostics-only — never appended to EventStore."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.reducer import reduce_events


class TestCommandRejectedDiagnostics(unittest.TestCase):
    def test_reject_split_writes_diagnostics_not_events(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            loop = Path(td)
            store = EventStore(loop / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            h.run_created(
                goal_id="g",
                memory_digest="sha256:" + "a" * 64,
                cognitive_tokens_max=1000,
                repairs_max=8,
            )
            before = len(store.read_all())
            res = h.commit_split({"split_node": "missing", "children": []})
            self.assertFalse(res.ok)
            self.assertTrue(res.rejected)
            self.assertEqual([], res.events)
            self.assertEqual(before, len(store.read_all()))
            diag = loop / "diagnostics.jsonl"
            self.assertTrue(diag.is_file())
            line = json.loads(diag.read_text(encoding="utf-8").strip())
            self.assertEqual(line["schema"], "eglk.command_rejected")
            self.assertEqual(line["command"], "split")
            self.assertEqual(line["reason"], "unknown_node")
            proj_before = reduce_events(store.read_all())
            proj_after = reduce_events(store.read_all())
            self.assertEqual(proj_before.run_status, proj_after.run_status)
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
