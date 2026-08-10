"""Adapter factory smoke — mock always; live backends optional."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.adapters.base import EpisodeRequest
from eglk_harness.domain.adapters.factory import create_adapter, adapter_names


class TestAdapterSmoke(unittest.TestCase):
    def test_factory_lists_backends(self) -> None:
        names = adapter_names()
        self.assertIn("mock", names)
        self.assertIn("codex", names)
        self.assertIn("claude_code", names)

    def test_mock_episode_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            adapter = create_adapter("mock", mock_mode="admit")
            req = EpisodeRequest(
                role="maker",
                prompt="test",
                workdir=workdir,
                expect="claim",
                meta={
                    "tick": 0,
                    "subgoal_id": "root",
                    "done_criteria": ["hello.txt exists"],
                    "contract_ref": "wc-1",
                    "obligation_refs": ["ob-1"],
                },
            )
            result = asyncio.run(adapter.run_episode(req))
            self.assertTrue(result.ok)
            self.assertIsInstance(result.parsed, dict)

    def test_live_adapter_construct_smoke(self) -> None:
        if os.environ.get("EGLK_ADAPTER_SMOKE_LIVE", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            self.skipTest("set EGLK_ADAPTER_SMOKE_LIVE=1 to run live adapter construct smoke")
        codex = create_adapter("codex")
        claude = create_adapter("claude_code")
        self.assertEqual(codex.name, "codex")
        self.assertEqual(claude.name, "claude_code")


if __name__ == "__main__":
    unittest.main()
