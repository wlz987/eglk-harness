"""Regression: root admit must stop the run loop (no spurious next tick)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.app import RunRequest, run
from eglk_harness.domain.product.init_project import init_project


def test_admit_root_stops_without_no_in_progress_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path)
    (tmp_path / ".goal.md").write_text(
        "# Stop\n\n- [ ] hello.txt exists\n",
        encoding="utf-8",
    )

    import eglk_harness.app as app_mod
    from eglk_harness.domain.adapters.mock import MockAdapter

    monkeypatch.setattr(app_mod, "create_adapter", lambda *a, **k: MockAdapter(mode="admit"))

    code = run(
        RunRequest(
            workdir=tmp_path,
            agent="mock",
            swarm="0",
            compile="off",
            max_ticks=8,
        )
    )
    assert code == 0
    # Manifest should not record spurious second-tick failure
    mans = list((tmp_path / ".local" / "runs").glob("*/manifest.json"))
    assert mans
    import json

    data = json.loads(mans[-1].read_text(encoding="utf-8"))
    assert data.get("stop_reason") == "root_admitted"
    assert int(data.get("ticks_run") or 0) == 1
    assert "no_in_progress_leaf" not in str(data.get("stop_reason"))
