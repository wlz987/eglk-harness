"""Refiner merge_suggest sidecar → tick begin apply (cross-tick merge)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.event_store import EventStore
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.run_loop import TickRunLoop
from eglk_harness.domain.product.init_project import init_project


def _bootstrap_two_leaf_goal(h: CommandHandler) -> None:
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


class TestCrossTickMergeSuggest(unittest.TestCase):
    def test_merge_suggest_applied_on_tick_begin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            goal_id = "merge-cross"
            loop = paths.ensure_loop_layout(workdir, goal_id)
            store = EventStore(loop / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf_goal(h)
            store.release_lease(holder="t")
            store.close()
            (loop / ".write_lease").unlink(missing_ok=True)

            cand = loop / "candidates"
            cand.mkdir(parents=True, exist_ok=True)
            (cand / "merge_suggest_001_0.json").write_text(
                json.dumps(
                    {
                        "parent_id": "root",
                        "nodes": ["root.01", "root.02"],
                        "into": "root.cross",
                        "title": "merged siblings",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            tick_loop = TickRunLoop(
                workdir=workdir,
                goal_id=goal_id,
                tick=1,
                goal_title="merge goal",
                done_criteria=["hello.txt exists"],
            )
            tick_loop.loop_dir = loop
            from eglk_harness.domain.kernel.event_runtime import RunEventContext

            tick_loop.ctx = RunEventContext(workdir, goal_id)
            tick_loop.ctx.acquire()
            tick_loop._apply_pending_merge_suggestions()
            tick_loop.ctx.export_projections(tick=1)
            tick_loop.ctx.release()

            store = EventStore(loop / "events.db")
            types = [e.type for e in store.read_all()]
            store.close()
            self.assertIn("MergeCommitted", types)
            self.assertFalse((cand / "merge_suggest_001_0.json").is_file())


if __name__ == "__main__":
    unittest.main()
