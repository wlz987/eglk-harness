"""Tests for eval environment probes."""

from pathlib import Path

from eglk_harness.domain.eval.eval_env_probes import collect_eval_env_status, doctor_checks_from_status


def test_collect_eval_env_status_keys():
    root = Path(__file__).resolve().parents[4] / "experiment" / "eval"
    if not root.is_dir():
        return
    st = collect_eval_env_status(root)
    assert "eval_root" in st
    assert "can_weave_smoke" in st
    checks = doctor_checks_from_status(st)
    names = {n for n, _, _ in checks}
    assert "eval_vllm_28000" in names
    assert "eval_weave_pack" in names


def test_doctor_checks_from_status_structure():
    st = {"vllm_127_28000": True, "weave_lh_pack_count": 116, "can_weave_full": True, "can_osworld_full": False}
    rows = doctor_checks_from_status(st)
    assert rows
    assert all(len(r) == 3 for r in rows)
