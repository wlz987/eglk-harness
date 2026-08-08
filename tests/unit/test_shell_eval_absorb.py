"""Shell/eval absorption tests — plugins, dashboard RO, update, eval scorer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from eglk_harness.domain.plugins.codex_computer_use import (
    COMPUTER_USE_PLUGIN_ID,
    CodexPluginError,
    CodexPluginState,
    get_codex_plugin_state,
    install_computer_use_plugin,
)
from eglk_harness.domain.eval.eval_runner import prepare_task_workdir, score_offline
from tests.helpers.eval_root import eval_root_for_tests
from eglk_harness.domain.product.observe.dashboard import assert_read_only_routes, list_routes, serve_dashboard
from eglk_harness.domain.product.update_check import _is_newer, check_update
from eglk_harness.domain.kernel.gate import decide


def test_dashboard_routes_read_only() -> None:
    assert_read_only_routes()
    joined = " ".join(list_routes()).lower()
    for bad in ("approve", "inject", "ask", "continue"):
        assert bad not in joined


def test_dashboard_rejects_post(tmp_path: Path) -> None:
    server = serve_dashboard(tmp_path, host="127.0.0.1", port=0, blocking=False)
    try:
        host, port = server.server_address[:2]
        import urllib.error
        import urllib.request

        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"http://{host}:{port}/api/status",
                    data=b"{}",
                    method="POST",
                    headers={"Content-Type": "application/json"},
                ),
                timeout=2,
            )
        assert ei.value.code == 405
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2) as resp:
            body = json.loads(resp.read().decode())
        assert body["mode"] == "read_only"
    finally:
        server.shutdown()
        server.server_close()


def test_is_newer_versions() -> None:
    assert _is_newer("0.2.0", "0.1.0")
    assert not _is_newer("0.1.0", "0.1.0")


def test_check_update_handles_404() -> None:
    class FakeResp:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import urllib.error

    with patch(
        "eglk_harness.domain.product.update_check.urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("x", 404, "nf", hdrs=None, fp=None),
    ):
        r = check_update()
    assert r.latest is None
    assert "PyPI" in r.detail or "pypi" in r.detail.lower() or "not yet" in r.detail


def test_codex_plugin_state_from_json() -> None:
    payload = {
        "installed": [
            {
                "pluginId": COMPUTER_USE_PLUGIN_ID,
                "installed": True,
                "enabled": True,
                "version": "1.0",
            }
        ],
        "available": [],
    }

    class R:
        stdout = json.dumps(payload)
        stderr = ""
        returncode = 0

    with patch("eglk_harness.domain.plugins.codex_computer_use._run_codex", return_value=R()):
        with patch("eglk_harness.domain.plugins.codex_computer_use._resolve_codex_binary", return_value="codex"):
            st = get_codex_plugin_state(COMPUTER_USE_PLUGIN_ID)
    assert st.ready and st.version == "1.0"


def test_install_plugin_already_ready() -> None:
    ready = CodexPluginState(COMPUTER_USE_PLUGIN_ID, True, True, True, "1")
    with patch(
        "eglk_harness.domain.plugins.codex_computer_use.get_codex_plugin_state", return_value=ready
    ):
        with patch("eglk_harness.domain.plugins.codex_computer_use._resolve_codex_binary", return_value="codex"):
            assert install_computer_use_plugin() is ready


def test_install_plugin_unavailable() -> None:
    missing = CodexPluginState(COMPUTER_USE_PLUGIN_ID, False, False, False)
    with patch(
        "eglk_harness.domain.plugins.codex_computer_use.get_codex_plugin_state", return_value=missing
    ):
        with patch("eglk_harness.domain.plugins.codex_computer_use._resolve_codex_binary", return_value="codex"):
            with pytest.raises(CodexPluginError):
                install_computer_use_plugin()


def test_eval_prepare_and_score(tmp_path: Path) -> None:
    eval_root = eval_root_for_tests()
    wd = tmp_path / "task"
    prepare_task_workdir(eval_root, suite="weave_thin", task_id="toy-hello", out_dir=wd)
    assert (wd / ".goal.md").is_file()
    (wd / "hello.txt").write_text("hello from eglk\n", encoding="utf-8")
    scored = score_offline(suite="weave_thin", task_id="toy-hello", workdir=wd, eval_root=eval_root)
    assert scored.ok


def test_gate_keys_never_include_scorer() -> None:
    # Regression: Gate still truth-blind after eval absorption
    claim = {
        "claim_id": "c1",
        "tick": 0,
        "maker_session_id": "m",
        "kind": "files",
        "done_progress": 1.0,
        "confidence": 0.9,
        "alternatives": [{"text": "a", "status": "reject"}],
        "payload": {"files": {"a.txt": "x"}},
        "step_review": {
            "gains": ["g"],
            "losses": ["l"],
            "benefits": ["b"],
            "risks": ["r"],
        },
    }
    evidence = {
        "evidence_id": "e1",
        "tick": 0,
        "checker_session_id": "c",
        "artifacts": [{"path": "a.txt", "kind": "file"}],
        "gaps": [],
        "integrity": "clean",
        "done_progress": 1.0,
        "confidence": 0.9,
    }
    # decide ignores unknown kwargs conceptually — only documented inputs
    d = decide(claim, evidence, quota={"cognitive_tokens": 0}, repair_counts={})
    kind = d.decision if hasattr(d, "decision") else d["decision"]
    assert kind in {"admit", "repair", "abort"}
