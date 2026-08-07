from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval.wa_hard import (
    ingest_agent_runs,
    score_from_eval_result,
)


def test_score_from_eval_result(tmp_path: Path) -> None:
    p = tmp_path / "eval_result.json"
    p.write_text(
        json.dumps(
            {
                "task_id": 108,
                "status": "success",
                "score": 1.0,
                "sites": ["shopping_admin"],
                "webarena_verified_version": "1.2.3",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = score_from_eval_result(p)
    assert out["success"] == 1.0
    assert out["status"] == "official_scored"
    assert out["task_id"] == "108"
    assert "admit" not in out


def test_ingest_agent_runs(tmp_path: Path) -> None:
    for tid, score, status in (("107", 0.0, "failure"), ("108", 1.0, "success")):
        d = tmp_path / tid
        d.mkdir()
        (d / "eval_result.json").write_text(
            json.dumps({"task_id": int(tid), "status": status, "score": score}) + "\n",
            encoding="utf-8",
        )
    (tmp_path / "109").mkdir()
    bundle = ingest_agent_runs(tmp_path, task_ids=["107", "108", "109"])
    assert bundle["count"] == 3
    assert bundle["success_count"] == 1
    by_id = {r["task_id"]: r for r in bundle["tasks"]}
    assert by_id["108"]["ok"] is True
    assert by_id["107"]["ok"] is False
    assert by_id["109"]["detail"] == "missing_eval_result"
