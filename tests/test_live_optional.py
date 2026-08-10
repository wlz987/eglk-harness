"""Optional live-backend smoke — skipped unless env flags set."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.adapters.factory import create_adapter


class TestLiveOptional(unittest.TestCase):
    def test_live_soak_bypass_codex(self) -> None:
        if os.environ.get("EGLK_SOAK_LIVE", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            self.skipTest("set EGLK_SOAK_LIVE=1 for live soak-bypass")
        from eglk_harness.domain.eval.bypass_soak import soak_bypass_roles

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            adapter = create_adapter("codex")
            report = asyncio.run(
                soak_bypass_roles(adapter, workdir, timeout_s=90.0, force=True)
            )
            self.assertTrue(report.ok)
            llm_hits = sum(1 for r in report.roles if r.source == "llm")
            self.assertGreater(llm_hits, 0)


if __name__ == "__main__":
    unittest.main()
