"""Plugin registry — list/community ids without network install."""

from __future__ import annotations

import unittest

from eglk_harness.domain.plugins import (
    CODEX_GUI_PLUGIN_ID,
    COMMUNITY_PLUGINS,
    community_plugin_ids,
    get_community_plugin,
    plugins_root,
)
from eglk_harness.domain.product.observe.dashboard import assert_read_only_routes


class TestPluginRegistry(unittest.TestCase):
    def test_community_plugins_registered(self) -> None:
        ids = community_plugin_ids()
        self.assertGreaterEqual(len(ids), 1)
        self.assertTrue(CODEX_GUI_PLUGIN_ID)
        for pid in ids:
            loaded = get_community_plugin(pid)
            self.assertEqual(loaded.plugin_id, pid)
            self.assertTrue(loaded.homepage.startswith("http"))

    def test_plugins_root_is_path(self) -> None:
        root = plugins_root()
        self.assertTrue(str(root).endswith("plugins") or "plugins" in str(root))

    def test_dashboard_forbidden_routes_absent(self) -> None:
        assert_read_only_routes()
        for bad in ("approve", "inject", "ask", "human_hook"):
            for route in __import__(
                "eglk_harness.domain.product.observe.dashboard",
                fromlist=["list_routes"],
            ).list_routes():
                self.assertNotIn(bad, route.lower())


if __name__ == "__main__":
    unittest.main()
