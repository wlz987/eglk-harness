"""package_agent_run_from_workdir for WA official HAR path."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval import wa_hard as wa


def test_package_agent_run_from_workdir(tmp_path: Path) -> None:
    workdir = tmp_path / "task"
    tid = "681"
    run = workdir / "agent_runs" / tid
    run.mkdir(parents=True)
    (run / "agent_response.json").write_text(
        json.dumps({"action": "navigate", "status": "UNKNOWN_ERROR", "results": None}),
        encoding="utf-8",
    )
    (run / "network.har").write_text("{}", encoding="utf-8")
    dest_root = tmp_path / "agent_runs"
    out = wa.package_agent_run_from_workdir(workdir, tid, dest_root)
    assert out["ok"] is True
    assert (dest_root / tid / "network.har").is_file()


def test_package_agent_run_missing(tmp_path: Path) -> None:
    out = wa.package_agent_run_from_workdir(tmp_path, "1", tmp_path / "out")
    assert out["ok"] is False
    assert "missing" in out
