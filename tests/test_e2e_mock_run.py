"""End-to-end: ``app._run_loop`` with mock agent → ``RunSucceeded`` + deliverable."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from eglk_harness.app import RunRequest, _run_loop
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.goal_parse import goal_id, read_goal_text
from eglk_harness.domain.kernel.loop_store import read_json
from eglk_harness.domain.product.init_project import init_project


class TestE2EMockRun(unittest.TestCase):
    def test_mock_run_loop_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir)
            paths.goal_path(workdir).write_text(
                "# Hello file\n\n## Done criteria\n- [ ] hello.txt exists\n",
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
                        max_ticks=8,
                        compile="off",
                    )
                )
            )

            rp = read_json(
                paths.loop_goal_dir(workdir, gid) / "projections" / "run_projection.json"
            )
            self.assertEqual(rp.get("run_status"), "succeeded")
            self.assertTrue((workdir / "hello.txt").is_file())
            self.assertEqual(result.get("stop_reason"), "terminal:succeeded")
            outcome = result.get("outcome") or {}
            self.assertTrue(outcome.get("ok"))

            manifest_path = Path(str(result.get("manifest") or ""))
            self.assertTrue(manifest_path.is_file())
            manifest_json = manifest_path.parent / "manifest.json"
            manifest = json.loads(manifest_json.read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("run_status"), "succeeded")
            self.assertTrue(str(manifest.get("event_log_hash") or "").startswith("sha256:"))

            from eglk_harness.domain.event_store import open_store

            loop_dir = paths.loop_goal_dir(workdir, gid)
            rp = read_json(loop_dir / "projections" / "run_projection.json")
            store = open_store(loop_dir)
            events = store.read_all()
            store.close()
            self.assertTrue(events)
            self.assertEqual(manifest.get("event_log_hash"), rp.get("last_hash"))
            self.assertEqual(manifest.get("event_log_hash"), events[-1].hash)

            quota_roles: set[str] = set()
            for ev in events:
                if ev.type != "QuotaUpdated":
                    continue
                by_role = (ev.payload or {}).get("cognitive_tokens_by_role") or {}
                if isinstance(by_role, dict):
                    quota_roles.update(str(k) for k in by_role)
            for role in ("maker", "checker", "explorer", "refiner"):
                self.assertIn(role, quota_roles)
            mem_types = [e.type for e in events]
            self.assertIn("MemoryCandidateWritten", mem_types)

