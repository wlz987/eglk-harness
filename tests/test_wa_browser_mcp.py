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
    extract_links,
    grid_filter_selector,
    grid_filter_submit_selectors,
    merge_observed_nav_payload,
)


class WaBrowserCommonTests(unittest.TestCase):
    def test_extract_links_relative_and_absolute(self) -> None:
        html = (
            "<a href='/admin/review/product/index/'>Reviews</a>"
            "<a href='http://127.0.0.1:7780/admin/catalog/'>Catalog</a>"
        )
        links = extract_links(html, "http://127.0.0.1:7780/admin/dashboard/")
        hrefs = {item["href"] for item in links}
        self.assertIn("http://127.0.0.1:7780/admin/review/product/index/", hrefs)

    def test_grid_filter_generic_pattern(self) -> None:
        sel = grid_filter_selector("reviewGrid", "detail")
        self.assertEqual(sel, "#reviewGrid_filter_detail")
        submits = grid_filter_submit_selectors("reviewGrid")
        self.assertTrue(any("reviewGrid" in s for s in submits))

    def test_merge_observed_nav_no_oracle_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / ".eglk-harness"
            harness.mkdir(parents=True)
            (harness / "task_start_urls.json").write_text(
                json.dumps({"start_urls": ["http://127.0.0.1:7780/admin"]}),
                encoding="utf-8",
            )
            (harness / "wa_env_contract.json").write_text(
                json.dumps(
                    {
                        "site_keys": ["shopping_admin"],
                        "environments": {
                            "shopping_admin": {
                                "urls": ["http://127.0.0.1:7780/admin"],
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
            self.assertEqual(payload["task_start_urls"], ["http://127.0.0.1:7780/admin"])
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
            dest = wa.materialize_task_start_urls(["http://127.0.0.1:7780/admin"], out)
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
