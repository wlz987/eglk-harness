"""Read-only dashboard — browse loop artifacts; never an approval gate."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.product.status import collect_status

# Forbidden write/approval verbs — tests assert absence from route table.
_FORBIDDEN_SEGMENTS = frozenset(
    {"approve", "inject", "continue", "stop", "ask", "instruction", "human_hook"}
)

def list_routes() -> list[str]:
    return [
        "GET /",
        "GET /api/status",
        "GET /api/tree",
        "GET /api/ticks",
        "GET /api/agent_logs",
        "GET /health",
    ]

def assert_read_only_routes() -> None:
    for route in list_routes():
        method, _, path = route.partition(" ")
        assert method == "GET", route
        for bad in _FORBIDDEN_SEGMENTS:
            assert bad not in path.lower(), route

class _Handler(BaseHTTPRequestHandler):
    workdir: Path

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(405, "Dashboard is read-only (no approval gate)")

    def do_PUT(self) -> None:  # noqa: N802
        self.send_error(405, "Dashboard is read-only (no approval gate)")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/health":
            self._json({"ok": True, "mode": "read_only"})
            return
        if path == "/api/status":
            report = collect_status(self.workdir)
            self._json(
                {
                    "workdir": str(self.workdir),
                    "mode": "read_only",
                    "banner": "只读观测 · 非审批闸",
                    "text": report.render(),
                    "quota": report.quota,
                    "selected_run": report.selected_run,
                }
            )
            return
        if path == "/api/tree":
            self._json(self._load_tree())
            return
        if path == "/api/ticks":
            self._json({"lines": self._load_ticks()})
            return
        if path == "/api/agent_logs":
            self._json(self._load_agent_logs())
            return
        if path == "/":
            self._html(_INDEX_HTML)
            return
        self.send_error(404)

    def _load_tree(self) -> dict[str, Any]:
        loop = paths.loop_root(self.workdir)
        if not loop.is_dir():
            return {"error": "no_loop"}
        goals = sorted(p for p in loop.iterdir() if p.is_dir())
        if not goals:
            return {"error": "empty"}
        goal_dir = goals[-1]
        tree_path = goal_dir / "projections" / "task_structure.json"
        if not tree_path.is_file():
            return {"goal_id": goal_dir.name, "tree": None}
        try:
            return {"goal_id": goal_dir.name, "tree": json.loads(tree_path.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            return {"goal_id": goal_dir.name, "error": "unreadable"}

    def _load_ticks(self) -> list[str]:
        loop = paths.loop_root(self.workdir)
        if not loop.is_dir():
            return []
        goals = sorted(p for p in loop.iterdir() if p.is_dir())
        if not goals:
            return []
        ticks = goals[-1] / "ticks.jsonl"
        if not ticks.is_file():
            return []
        return ticks.read_text(encoding="utf-8").splitlines()[-50:]

    def _load_agent_logs(self) -> dict[str, Any]:
        """List visible/steps sidecars under the newest loop (read-only)."""
        loop = paths.loop_root(self.workdir)
        if not loop.is_dir():
            return {"files": [], "error": "no_loop"}
        goals = sorted(p for p in loop.iterdir() if p.is_dir())
        if not goals:
            return {"files": [], "error": "empty"}
        logs_dir = goals[-1] / "agent_logs"
        if not logs_dir.is_dir():
            return {"goal_id": goals[-1].name, "files": []}
        files: list[dict[str, str]] = []
        for path in sorted(logs_dir.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            kind = "raw"
            if name.endswith(".visible.txt"):
                kind = "visible"
            elif name.endswith(".steps.json"):
                kind = "steps"
            elif name.endswith(".jsonl"):
                kind = "jsonl"
            files.append({"name": name, "kind": kind, "path": str(path)})
        return {"goal_id": goals[-1].name, "files": files[-40:]}

    def _json(self, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>eglk-harness dashboard (read-only)</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; max-width: 960px; }
    .banner { background: #f0f4f8; padding: 0.75rem 1rem; border-left: 4px solid #334155; }
    pre { background: #0f172a; color: #e2e8f0; padding: 1rem; overflow: auto; }
    a { color: #0369a1; }
  </style>
</head>
<body>
  <p class="banner"><strong>只读观测 · 非审批闸</strong> — 无 approve / inject / ask。</p>
  <h1>eglk-harness</h1>
  <p>
    <a href="/api/status">/api/status</a> ·
    <a href="/api/tree">/api/tree</a> ·
    <a href="/api/ticks">/api/ticks</a> ·
    <a href="/api/agent_logs">/api/agent_logs</a> ·
    <a href="/health">/health</a>
  </p>
  <pre id="out">loading…</pre>
  <script>
    fetch('/api/status').then(r => r.json()).then(d => {
      document.getElementById('out').textContent = d.text || JSON.stringify(d, null, 2);
    }).catch(e => { document.getElementById('out').textContent = String(e); });
  </script>
</body>
</html>
"""

def serve_dashboard(
    workdir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    blocking: bool = True,
) -> ThreadingHTTPServer:
    """Start read-only HTTP server. Returns server (caller may shutdown)."""
    assert_read_only_routes()
    workdir = workdir.resolve()
    handler = type("DashHandler", (_Handler,), {"workdir": workdir})
    server = ThreadingHTTPServer((host, port), handler)
    if blocking:
        print(
            f"eglk-harness dashboard (read-only) http://{host}:{port}/  workdir={workdir}",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    else:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    return server
