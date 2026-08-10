"""Integration: handler-level split → merge → depends_on promotion flows."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.event_store import EventStore, open_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.advisors import (
    build_mechanical_merge_candidate,
    build_mechanical_split_candidate,
)
from eglk_harness.domain.kernel.command_handler import CommandHandler
from eglk_harness.domain.kernel.goal_parse import goal_id, read_goal_text
from eglk_harness.domain.kernel.scheduler import deps_satisfied, select_ready_node
from eglk_harness.domain.product.init_project import init_project


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


class TestHandlerMergeRoundtrip(unittest.TestCase):
    def test_partition_split_then_mechanical_merge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = EventStore(Path(td) / "events.db")
            store.acquire_lease(holder="t")
            h = CommandHandler(store)
            _bootstrap_two_leaf_goal(h)
            mech = build_mechanical_merge_candidate(h.projection(), step=2)
            self.assertIsNotNone(mech)
            merged = h.commit_merge(mech, actor="governor")
            self.assertTrue(merged.ok, merged.error)
            proj = h.projection()
            into = mech["into"]
            self.assertIn(into, proj.nodes)
            self.assertEqual(proj.nodes[into].status, "ready")
            self.assertEqual(proj.nodes["root.01"].status, "superseded")
            self.assertEqual(proj.nodes["root.02"].status, "superseded")
            types = [e.type for e in store.read_all()]
            self.assertIn("MergeProposed", types)
            self.assertIn("MergeCommitted", types)
            self.assertIn("NodeReady", types)
            store.release_lease(holder="t")
            store.close()


class TestMockRunIntegration(unittest.TestCase):
    def test_mock_single_leaf_run_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            paths.goal_path(workdir).write_text(
                "# Single deliverable\n\n## Done criteria\n- [ ] hello.txt exists\n",
                encoding="utf-8",
            )
            text = read_goal_text(workdir)
            gid = goal_id(text)

            result = asyncio.run(
                _run_loop(
                    RunRequest(
                        workdir=workdir,
                        agent="mock",
                        fake_mode="admit",
                        max_ticks=10,
                        compile="off",
                        swarm="0",
                    )
                )
            )

            loop_dir = paths.loop_goal_dir(workdir, gid)
            store = open_store(loop_dir)
            types = [e.type for e in store.read_all()]
            store.close()
            self.assertIn("RunSucceeded", types)
            self.assertTrue((workdir / "hello.txt").is_file())
            self.assertTrue(result.get("outcome", {}).get("ok"))


class TestDependsOnPromotion(unittest.TestCase):
    def test_split_chain_promotes_second_child_after_admit(self) -> None:
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
                    "title": "one criterion",
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
            h.commit_split(mech, actor="governor")
            proj = h.projection()
            first = mech["children"][0]["id"]
            second = mech["children"][1]["id"]
            self.assertEqual(select_ready_node(proj), first)
            self.assertFalse(deps_satisfied(proj, second))
            store.release_lease(holder="t")
            store.close()


if __name__ == "__main__":
    unittest.main()
