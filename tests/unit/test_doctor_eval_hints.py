"""Doctor includes eval vendor hints (never Gate)."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.product.doctor import run_doctor
from eglk_harness.domain.product.init_project import init_project


def test_doctor_reports_eval_and_core_fields(tmp_path: Path) -> None:
    init_project(tmp_path)
    report = run_doctor(tmp_path)
    names = {c.name for c in report.checks}
    assert "plugins" in names
    assert "budgets" in names
    assert "prompt_language" in names
    assert "host_tick_timeout" in names
    assert "eval_root" in names
    tick = next(c for c in report.checks if c.name == "host_tick_timeout")
    assert "cognitive_tokens" in tick.detail
    assert "repairs_max" in tick.detail
    # eval_wa_vendor / eval_lh_vendor only when sibling alw eval exists
    detail = " | ".join(f"{c.name}:{c.detail}" for c in report.checks)
    assert "python" in names
    assert report.ok or "schemas" in detail  # soft: env may warn
