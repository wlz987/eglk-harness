"""Tests for Maker dual episode and mechanical claim fallback."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.kernel.worldref import apply_claim_actions
from eglk_harness.domain.runtime.mechanical_claim import synthesize_mechanical_claim
from eglk_harness.domain.runtime.maker_dual_episode import (
    maker_dual_episode_enabled,
    mechanical_claim_first_enabled,
    run_maker_dual_episode,
)


class _ClaimFailAdapter:
    name = "claim_fail"
    claim_calls = 0

    async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
        if request.expect == "text":
            return EpisodeResult(ok=True, text="work done", backend=self.name)
        _ClaimFailAdapter.claim_calls += 1
        return EpisodeResult(ok=False, error="unparseable", text="not json", backend=self.name)


class MakerDualEpisodeTests(unittest.TestCase):
    def test_dual_enabled_by_default_with_tools(self) -> None:
        self.assertTrue(maker_dual_episode_enabled(True))
        os.environ["EGLK_MAKER_DUAL_EPISODE"] = "0"
        self.assertFalse(maker_dual_episode_enabled(True))
        del os.environ["EGLK_MAKER_DUAL_EPISODE"]

    def test_mechanical_claim_from_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "agent_runs" / "7").mkdir(parents=True)
            (workdir / "agent_runs" / "7" / "agent_response.json").write_text(
                '{"status":"SUCCESS"}\n',
                encoding="utf-8",
            )
            (workdir / "agent_runs" / "7" / "network.har").write_text(
                json.dumps({"log": {"version": "1.2", "entries": [{"request": {}}]}}) + "\n",
                encoding="utf-8",
            )
            boundary = [
                "MUST_EXIST: agent_runs/7/agent_response.json",
                "MUST_EXIST: agent_runs/7/network.har (network capture)",
            ]
            claim = synthesize_mechanical_claim(
                workdir=workdir,
                title="t",
                subgoal_id="root",
                contract_ref="wc-test",
                world_revision=0,
                obligation_refs=["ob-1"],
                boundary=boundary,
                tick=0,
            )
            self.assertIsNotNone(claim)
            assert claim is not None
            kinds = [a.get("kind") for a in claim.get("actions") or []]
            self.assertIn("file_write", kinds)
            self.assertEqual(claim.get("note"), "mechanical_claim_from_disk")
            written = apply_claim_actions(workdir, claim.get("actions"))
            self.assertIn("agent_runs/7/agent_response.json", written)

    def test_mechanical_first_skips_claim_llm(self) -> None:
        os.environ["EGLK_MAKER_MECHANICAL_FIRST"] = "1"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                (workdir / "hello.txt").write_text("ok\n", encoding="utf-8")
                boundary = ["MUST_EXIST: hello.txt"]
                meta = {
                    "tick": 0,
                    "subgoal_id": "root",
                    "done_criteria": ["hello.txt exists"],
                    "contract_ref": "wc-first",
                    "obligation_refs": ["ob-1"],
                    "world_revision": 0,
                }
                _ClaimFailAdapter.claim_calls = 0
                self.assertTrue(mechanical_claim_first_enabled())
                result = asyncio.run(
                    run_maker_dual_episode(
                        _ClaimFailAdapter(),
                        workdir=workdir,
                        leaf_block="[LEAF]\nid: root",
                        boundary=boundary,
                        title="hello leaf",
                        subgoal_id="root",
                        tick=0,
                        contract_ref="wc-first",
                        obligation_refs=["ob-1"],
                        world_revision=0,
                        tools_allowed=True,
                        mcp_config=None,
                        add_dirs=(),
                        model=None,
                        timeout_s=60.0,
                        tee_path=None,
                        meta=meta,
                    )
                )
                self.assertTrue(result.ok)
                self.assertEqual(_ClaimFailAdapter.claim_calls, 0)
                assert isinstance(result.parsed, dict)
                self.assertEqual(result.parsed.get("note"), "mechanical_claim_from_boundary")
        finally:
            os.environ.pop("EGLK_MAKER_MECHANICAL_FIRST", None)

    def test_mechanical_first_enabled_by_default(self) -> None:
        os.environ.pop("EGLK_MAKER_MECHANICAL_FIRST", None)
        self.assertTrue(mechanical_claim_first_enabled())

    def test_mechanical_first_disabled_runs_claim_llm(self) -> None:
        os.environ["EGLK_MAKER_MECHANICAL_FIRST"] = "0"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                (workdir / "hello.txt").write_text("ok\n", encoding="utf-8")
                boundary = ["MUST_EXIST: hello.txt"]
                meta = {
                    "tick": 0,
                    "subgoal_id": "root",
                    "done_criteria": ["hello.txt exists"],
                    "contract_ref": "wc-first-off",
                    "obligation_refs": ["ob-1"],
                    "world_revision": 0,
                }
                _ClaimFailAdapter.claim_calls = 0
                result = asyncio.run(
                    run_maker_dual_episode(
                        _ClaimFailAdapter(),
                        workdir=workdir,
                        leaf_block="[LEAF]\nid: root",
                        boundary=boundary,
                        title="hello leaf",
                        subgoal_id="root",
                        tick=0,
                        contract_ref="wc-first-off",
                        obligation_refs=["ob-1"],
                        world_revision=0,
                        tools_allowed=True,
                        mcp_config=None,
                        add_dirs=(),
                        model=None,
                        timeout_s=60.0,
                        tee_path=None,
                        meta=meta,
                    )
                )
                self.assertTrue(result.ok)
                self.assertGreaterEqual(_ClaimFailAdapter.claim_calls, 1)
        finally:
            del os.environ["EGLK_MAKER_MECHANICAL_FIRST"]

    def test_dual_episode_mechanical_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            hello = workdir / "hello.txt"
            hello.write_text("ok\n", encoding="utf-8")
            boundary = ["MUST_EXIST: hello.txt"]
            meta = {
                "tick": 0,
                "subgoal_id": "root",
                "done_criteria": ["hello.txt exists"],
                "contract_ref": "wc-dual",
                "obligation_refs": ["ob-1"],
                "world_revision": 0,
            }
            result = asyncio.run(
                run_maker_dual_episode(
                    _ClaimFailAdapter(),
                    workdir=workdir,
                    leaf_block="[LEAF]\nid: root",
                    boundary=boundary,
                    title="hello leaf",
                    subgoal_id="root",
                    tick=0,
                    contract_ref="wc-dual",
                    obligation_refs=["ob-1"],
                    world_revision=0,
                    tools_allowed=True,
                    mcp_config=None,
                    add_dirs=(),
                    model=None,
                    timeout_s=60.0,
                    tee_path=None,
                    meta=meta,
                )
            )
            self.assertTrue(result.ok)
            self.assertIsInstance(result.parsed, dict)
            assert isinstance(result.parsed, dict)
            self.assertEqual(result.parsed.get("note"), "mechanical_claim_from_boundary")

    def test_mock_dual_work_then_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            meta = {
                "tick": 0,
                "subgoal_id": "root",
                "done_criteria": ["hello.txt exists"],
                "contract_ref": "wc-mock",
                "obligation_refs": ["ob-1"],
                "world_revision": 0,
            }
            result = asyncio.run(
                run_maker_dual_episode(
                    MockAdapter(),
                    workdir=workdir,
                    leaf_block="[LEAF]\nid: root",
                    boundary=["MUST_EXIST: hello.txt"],
                    title="mock",
                    subgoal_id="root",
                    tick=0,
                    contract_ref="wc-mock",
                    obligation_refs=["ob-1"],
                    world_revision=0,
                    tools_allowed=True,
                    mcp_config=None,
                    add_dirs=(),
                    model=None,
                    timeout_s=60.0,
                    tee_path=None,
                    meta=meta,
                )
            )
            self.assertTrue(result.ok)
            self.assertIsInstance(result.parsed, dict)
            assert isinstance(result.parsed, dict)
            self.assertIn("actions", result.parsed)


if __name__ == "__main__":
    unittest.main()
