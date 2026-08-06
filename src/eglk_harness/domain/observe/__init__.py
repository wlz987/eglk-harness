"""Read-only observation surfaces (never approval gates)."""

from eglk_harness.domain.observe.dashboard import assert_read_only_routes, list_routes, serve_dashboard

__all__ = ["assert_read_only_routes", "list_routes", "serve_dashboard"]
