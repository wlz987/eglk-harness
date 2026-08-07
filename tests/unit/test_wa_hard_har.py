"""WA-Hard HAR-offline scorer (Manifest-only)."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.eval import wa_hard as wa


FIXTURES = Path("/home/wlz/alw/experiment/eval/wa_hard/fixtures/traces")


def test_score_har_offline_pass() -> None:
    path = FIXTURES / "pass_trace.json"
    if not path.is_file():
        import pytest

        pytest.skip("alw fixtures missing")
    scores = wa.score_har_offline(path)
    assert scores["success"] == 1.0
    assert scores["judge"] == "eglk_har_offline"
    assert "admit" not in scores
    assert scores["status"] == "har_offline_scored"


def test_score_har_offline_fail() -> None:
    path = FIXTURES / "fail_trace.json"
    if not path.is_file():
        import pytest

        pytest.skip("alw fixtures missing")
    scores = wa.score_har_offline(path)
    assert scores["success"] == 0.0
    assert scores["answer_match"] is False


def test_vendor_status_never_raises(tmp_path: Path) -> None:
    st = wa.vendor_status(tmp_path)
    assert "can_run_live_hard" in st
    assert st["vendor_ready"] is False
