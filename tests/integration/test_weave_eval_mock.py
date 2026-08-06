"""Integration: weave_thin mock prepare + offline score (Gate-blind)."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.eval.eval_runner import default_eval_root, prepare_task_workdir, score_offline
from eglk_harness.domain.product.init_project import init_project


def test_weave_thin_offline_score_after_materialize(tmp_path: Path):
    root = default_eval_root()
    if root is None:
        # Fallback: design-repo relative from this checkout
        cand = Path(__file__).resolve().parents[3] / "experiment" / "eval"
        if not cand.is_dir():
            import pytest

            pytest.skip("experiment/eval not found")
        root = cand
    out = tmp_path / "wd"
    prepare_task_workdir(root, suite="weave_thin", task_id="toy-hello", out_dir=out)
    init_project(out)
    (out / "hello.txt").write_text("hello from eglk\n", encoding="utf-8")
    scored = score_offline(suite="weave_thin", task_id="toy-hello", workdir=out, eval_root=root)
    assert scored.ok
    assert scored.scores.get("contains_ok") is True
