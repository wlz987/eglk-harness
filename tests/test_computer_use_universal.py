"""Universal computer-use plugin surface — MCP resolve, allowlist enrich, prompts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eglk_harness.domain.adapters.mcp import resolve_mcp_config
from eglk_harness.domain.adapters.tool_policy import resolve_role_tool_profile
from eglk_harness.domain.memory.skills import render_prompt
from eglk_harness.domain.plugins.computer_use import (
    computer_use_enabled,
    enrich_mcp_allowlist,
    doctor_computer_use_detail,
)
from eglk_harness.domain.plugins.state import record_install, write_mcp_config


class TestComputerUseUniversal(unittest.TestCase):
    def test_enrich_allowlist_adds_community_server(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "plugins"
            os.environ["EGLK_PLUGINS_ROOT"] = str(root)
            os.environ["EGLK_COMPUTER_USE"] = "on"
            os.environ["EGLK_AGENT"] = "codex"
            config = write_mcp_config(
                "open-computer-use",
                "codex",
                server_name="open-computer-use",
                command="open-computer-use",
                args=["mcp"],
            )
            record_install(
                "open-computer-use",
                agents=["codex"],
                mcp_configs={"codex": str(config)},
                mcp_server_name="open-computer-use",
            )
            os.environ["EGLK_MCP_ALLOW_MAKER"] = "search"
            allow = enrich_mcp_allowlist("maker", frozenset({"search"}), env=os.environ)
            self.assertIn("open-computer-use", allow or frozenset())
            profile = resolve_role_tool_profile("maker", env=os.environ)
            self.assertIn("open-computer-use", profile.mcp_server_allowlist or frozenset())

    def test_resolve_mcp_config_uses_installed_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "plugins"
            os.environ["EGLK_PLUGINS_ROOT"] = str(root)
            os.environ["EGLK_COMPUTER_USE"] = "on"
            config = write_mcp_config(
                "clawdcursor",
                "claude_code",
                server_name="clawdcursor",
                command="clawdcursor",
                args=["mcp", "--compact"],
            )
            record_install(
                "clawdcursor",
                agents=["claude_code"],
                mcp_configs={"claude_code": str(config)},
                mcp_server_name="clawdcursor",
            )
            resolved = resolve_mcp_config(None, env=os.environ, agent="claude_code")
            self.assertIsNotNone(resolved)
            self.assertTrue(resolved.is_file())

    def test_computer_use_off_skips_enrich(self) -> None:
        env = {"EGLK_COMPUTER_USE": "off", "EGLK_MCP_ALLOW_MAKER": "search"}
        allow = enrich_mcp_allowlist("maker", frozenset({"search"}), env=env)
        self.assertEqual(frozenset({"search"}), allow)

    def test_render_prompt_injects_fragment_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "plugins"
            os.environ["EGLK_PLUGINS_ROOT"] = str(root)
            os.environ["EGLK_COMPUTER_USE"] = "on"
            config = write_mcp_config(
                "open-computer-use",
                "codex",
                server_name="open-computer-use",
                command="open-computer-use",
                args=["mcp"],
            )
            record_install(
                "open-computer-use",
                agents=["codex"],
                mcp_configs={"codex": str(config)},
                mcp_server_name="open-computer-use",
            )
            prompt = render_prompt("maker", leaf_block="[leaf]", workdir=Path(td))
            self.assertIn("Computer-use", prompt)
            self.assertIn("real screen captures", prompt)

    def test_doctor_detail_auto_mode(self) -> None:
        with mock.patch(
            "eglk_harness.domain.plugins.computer_use.collect_computer_use_status",
            return_value=[],
        ):
            os.environ["EGLK_COMPUTER_USE"] = "auto"
            ok, detail = doctor_computer_use_detail()
            self.assertTrue(ok)
            self.assertIn("mode=auto", detail)

    def test_doctor_fails_when_forced_on_without_plugin(self) -> None:
        os.environ["EGLK_COMPUTER_USE"] = "on"
        with mock.patch(
            "eglk_harness.domain.plugins.computer_use.active_plugin_for_agent",
            return_value=None,
        ):
            with mock.patch(
                "eglk_harness.domain.plugins.computer_use.collect_computer_use_status",
                return_value=[],
            ):
                ok, detail = doctor_computer_use_detail()
                self.assertFalse(ok)
                self.assertIn("no plugin ready", detail)

    def tearDown(self) -> None:
        for key in (
            "EGLK_PLUGINS_ROOT",
            "EGLK_COMPUTER_USE",
            "EGLK_AGENT",
            "EGLK_MCP_ALLOW_MAKER",
        ):
            os.environ.pop(key, None)


if __name__ == "__main__":
    unittest.main()
