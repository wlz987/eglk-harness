"""Format-repair and tools-off policy coverage."""

from __future__ import annotations

import os
import unittest

from eglk_harness.domain.adapters.base import EpisodeRequest
from eglk_harness.domain.adapters.codex import CodexAdapter
from eglk_harness.domain.adapters.tool_policy import tools_forced_off


class ToolPolicyTests(unittest.TestCase):
    def test_format_repair_role_tools_off(self) -> None:
        os.environ["EGLK_TOOLS_OFF_ROLES"] = "format-repair"
        try:
            self.assertTrue(tools_forced_off("format-repair"))
            self.assertFalse(tools_forced_off("maker"))
        finally:
            os.environ.pop("EGLK_TOOLS_OFF_ROLES", None)

    def test_codex_build_argv_no_mcp_when_tools_off(self) -> None:
        adapter = CodexAdapter()
        req = EpisodeRequest(
            workdir="/tmp",
            prompt="hi",
            expect="text",
            tools_allowed=False,
            role="format-repair",
        )
        argv = adapter.build_argv(req)
        joined = " ".join(argv)
        self.assertNotIn("mcp_servers", joined)

    def test_codex_mcp_argv_not_duplicated(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            mcp = Path(tmp) / "mcp.json"
            mcp.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "wa-scout": {
                                "command": "python3",
                                "args": ["scout.py"],
                                "env": {"X": "1"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            adapter = CodexAdapter(mcp_config=mcp)
            req = EpisodeRequest(
                workdir="/tmp",
                prompt="hi",
                expect="text",
                tools_allowed=True,
                role="maker",
                mcp_config=mcp,
            )
            argv = adapter.build_argv(req)
            joined = " ".join(argv)
            self.assertEqual(joined.count("mcp_servers.wa-scout="), 1)


if __name__ == "__main__":
    unittest.main()
