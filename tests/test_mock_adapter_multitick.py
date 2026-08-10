"""Mock adapter multi-role episodes — governor merge + full tick path."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.adapters.base import EpisodeRequest
from eglk_harness.domain.adapters.factory import create_adapter
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.goal_parse import goal_id, read_goal_text
from eglk_harness.domain.product.init_project import init_project


class TestMockAdapterMultiRole(unittest.TestCase):
    def test_mock_governor_merge_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            adapter = create_adapter("mock")
            req = EpisodeRequest(
                role="governor",
                prompt="merge",
                workdir=workdir,
                expect="text",
                meta={
                    "tick": 2,
                    "subgoal_id": "root",
                    "action": "merge",
                    "merge_parent_id": "root",
                    "merge_node_ids": ["root.01", "root.02"],
                    "merge_into": "root.m002",
                },
            )
            result = asyncio.run(adapter.run_episode(req))
            self.assertTrue(result.ok)
            doc = json.loads(result.text or "{}")
            self.assertEqual(doc.get("into"), "root.m002")
            self.assertIn("root.01", doc.get("node_ids") or [])

    def test_mock_multi_tick_run_with_swarm_off(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir, force=True)
            paths.goal_path(workdir).write_text(
                "# Multi tick\n\n## Done criteria\n- [ ] hello.txt exists\n",
                encoding="utf-8",
            )
            gid = goal_id(read_goal_text(workdir))
            result = asyncio.run(
                _run_loop(
                    RunRequest(
                        workdir=workdir,
                        agent="mock",
                        fake_mode="admit",
                        max_ticks=6,
                        compile="off",
                        swarm="0",
                    )
                )
            )
            self.assertTrue(result.get("outcome", {}).get("ok"))
            loop_dir = paths.loop_goal_dir(workdir, gid)
            from eglk_harness.domain.event_store import open_store

            store = open_store(loop_dir)
            types = [e.type for e in store.read_all()]
            store.close()
            self.assertIn("RunSucceeded", types)
            self.assertTrue((workdir / "hello.txt").is_file())


if __name__ == "__main__":
    unittest.main()
