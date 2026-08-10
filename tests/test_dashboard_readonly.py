"""Dashboard read-only routes and HTTP smoke."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.product.observe.dashboard import (
    assert_read_only_routes,
    list_routes,
    serve_dashboard,
)


class TestDashboardReadOnly(unittest.TestCase):
    def test_routes_are_get_only(self) -> None:
        assert_read_only_routes()
        routes = list_routes()
        self.assertTrue(any("/api/status" in r for r in routes))
        for route in routes:
            self.assertTrue(route.startswith("GET "))

    def test_health_endpoint_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            init_project(workdir)
            server = serve_dashboard(workdir, host="127.0.0.1", port=0, blocking=False)
            port = server.server_address[1]
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("ok"))
                self.assertEqual("read_only", data.get("mode"))
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as resp:
                    status = json.loads(resp.read().decode("utf-8"))
                self.assertEqual("read_only", status.get("mode"))
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
