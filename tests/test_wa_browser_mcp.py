"""Tests for WA browser MCP — no navigation oracle in eval overlay."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from eglk_harness.domain.eval.loader import load_suite_module
from tests.conftest import default_eval_root

EVAL_ROOT = default_eval_root()
MCP_DIR = EVAL_ROOT / "wa_hard" / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from wa_browser_common import (  # noqa: E402
    credentials_for_site,
    extract_links,
    merge_observed_nav_payload,
    pack_site_key_from_arg,
    site_env_map_from_config,
)


class WaBrowserCommonTests(unittest.TestCase):
    def test_extract_links_relative_and_absolute(self) -> None:
        base = "http://example.test/app/"
        html = (
            "<a href='/items/list'>Items</a>"
            "<a href='http://other.test/catalog'>Catalog</a>"
        )
        links = extract_links(html, base)
        hrefs = {item["href"] for item in links}
        self.assertIn("http://example.test/items/list", hrefs)
        self.assertIn("http://other.test/catalog", hrefs)

    def test_site_env_map_from_config(self) -> None:
        cfg = {
            "environments": {
                "__SHOPPING_ADMIN__": {"urls": ["http://127.0.0.1:1/admin"]},
                "__GITLAB__": {"urls": ["http://127.0.0.1:2"]},
            }
        }
        m = site_env_map_from_config(cfg)
        self.assertEqual(m.get("shopping_admin"), "__SHOPPING_ADMIN__")
        self.assertEqual(m.get("gitlab"), "__GITLAB__")

    def test_pack_site_key_from_env_key(self) -> None:
        cfg = {
            "environments": {
                "__SHOPPING_ADMIN__": {
                    "urls": ["http://127.0.0.1:7780/admin"],
                    "credentials": {"username": "admin", "password": "admin1234"},
                }
            }
        }
        self.assertEqual(pack_site_key_from_arg("shopping_admin", cfg), "shopping_admin")
        self.assertEqual(pack_site_key_from_arg("__SHOPPING_ADMIN__", cfg), "shopping_admin")
        self.assertIsNone(pack_site_key_from_arg("__UNKNOWN__", cfg))

    def test_credentials_for_site_accepts_pack_and_env_key(self) -> None:
        cfg = {
            "environments": {
                "__SHOPPING_ADMIN__": {
                    "urls": ["http://127.0.0.1:7780/admin"],
                    "credentials": {"username": "admin", "password": "admin1234"},
                }
            }
        }
        by_pack = credentials_for_site("shopping_admin", cfg)
        by_env = credentials_for_site("__SHOPPING_ADMIN__", cfg)
        self.assertIsNotNone(by_pack)
        self.assertIsNotNone(by_env)
        assert by_pack is not None and by_env is not None
        self.assertEqual(by_pack["site_key"], "shopping_admin")
        self.assertEqual(by_env["site_key"], "shopping_admin")
        self.assertEqual(by_pack["env_key"], "__SHOPPING_ADMIN__")
        self.assertEqual(by_pack["username"], "admin")

    def test_merge_observed_nav_no_oracle_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / ".eglk-harness"
            harness.mkdir(parents=True)
            (harness / "task_start_urls.json").write_text(
                json.dumps({"start_urls": ["http://example.test/start"]}),
                encoding="utf-8",
            )
            (harness / "wa_env_contract.json").write_text(
                json.dumps(
                    {
                        "site_keys": ["site_a"],
                        "environments": {
                            "site_a": {
                                "urls": ["http://example.test/start"],
                                "has_credentials": True,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            scout = harness / "scout"
            scout.mkdir()
            (scout / "navigation_hints.json").write_text(
                json.dumps({"links": [{"href": "http://x/observed", "text": "Observed"}]}),
                encoding="utf-8",
            )
            payload = merge_observed_nav_payload(root)
            self.assertEqual(payload["task_start_urls"], ["http://example.test/start"])
            self.assertEqual(payload["scout_link_count"], 1)
            self.assertNotIn("known_admin_paths", payload)
            self.assertNotIn("site_navigation_hints", payload)


class WaHardEnvContractTests(unittest.TestCase):
    def test_materialize_wa_env_contract_no_passwords(self) -> None:
        wa = load_suite_module("wa_hard", EVAL_ROOT)
        cfg = EVAL_ROOT / "wa_hard" / "config.local.json.example"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            dest = wa.materialize_wa_env_contract(
                EVAL_ROOT, ["shopping_admin"], out, config_path=cfg
            )
            self.assertIsNotNone(dest)
            assert dest is not None
            data = json.loads(dest.read_text(encoding="utf-8"))
            self.assertIn("shopping_admin", data["environments"])
            block = data["environments"]["shopping_admin"]
            self.assertTrue(block.get("has_credentials"))
            self.assertNotIn("password", json.dumps(block))

    def test_materialize_task_start_urls(self) -> None:
        wa = load_suite_module("wa_hard", EVAL_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            dest = wa.materialize_task_start_urls(["http://example.test/entry"], out)
            self.assertIsNotNone(dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(data["source"], "agent-input-get")

    def test_materialize_agent_response_hint_writes_env_contract(self) -> None:
        wa = load_suite_module("wa_hard", EVAL_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            path = wa.materialize_agent_response_hint(EVAL_ROOT, "11", out)
            self.assertIsNotNone(path)
            self.assertTrue((out / ".eglk-harness" / "wa_env_contract.json").is_file())
            hint = json.loads((out / ".eglk-harness" / "deliverable_hint.json").read_text())
            self.assertNotIn("site_keys", hint)


if __name__ == "__main__":
    unittest.main()
