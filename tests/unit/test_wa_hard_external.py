from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.eval.wa_hard import score_external


def test_score_external_reads_scores(tmp_path: Path):
    p = tmp_path / "result.json"
    p.write_text('{"scores": {"success": 1.0}, "task_id": "t1"}\n', encoding="utf-8")
    out = score_external(p)
    assert out["success"] == 1.0
    assert out["status"] == "external_scored"
    assert "admit" not in out
