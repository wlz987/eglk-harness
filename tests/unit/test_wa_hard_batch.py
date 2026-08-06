"""WA-Hard pack + batch runner (scores never feed Gate)."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval import wa_hard as wa_hard_mod


def test_load_pack_prefers_pack_json(tmp_path: Path) -> None:
    root = tmp_path / "wa_hard"
    root.mkdir()
    (root / "pack.example.json").write_text(
        json.dumps({"tasks": [{"id": "ex-only", "intent": "x", "sites": []}]}),
        encoding="utf-8",
    )
    (root / "pack.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": f"t{i}", "intent": f"intent {i}", "sites": ["s"]}
                    for i in range(5)
                ]
            }
        ),
        encoding="utf-8",
    )
    tasks = wa_hard_mod.load_pack_index(tmp_path)
    assert len(tasks) == 5
    assert tasks[0].task_id == "t0"


def test_run_batch_writes_summary(tmp_path: Path) -> None:
    eval_root = Path("/home/wlz/alw/experiment/eval")
    if not (eval_root / "wa_hard" / "pack.json").is_file():
        import pytest

        pytest.skip("alw experiment/eval pack missing")
    out = tmp_path / "batch"
    summary = wa_hard_mod.run_batch(eval_root, out_root=out, limit=5, prepare_only=False)
    assert summary["count"] == 5
    assert Path(summary["summary_path"]).is_file()
    assert (out / "wa-hard-001-admin-lookup" / ".goal.md").is_file()
    assert "never Gate" in summary["note"]
    assert summary["tasks"][0]["scores"]["suite"] == "wa_hard"
