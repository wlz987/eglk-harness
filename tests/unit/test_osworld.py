"""OSWorld aux unit tests."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval import osworld as os


def test_score_external(tmp_path: Path) -> None:
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"scores": {"success": 1.0}}), encoding="utf-8")
    s = os.score_external(p)
    assert s["success"] == 1.0
    assert s["status"] == "external_scored"
    assert "admit" not in s


def test_vendor_status(tmp_path: Path) -> None:
    st = os.vendor_status(tmp_path)
    assert "vendor_ready" in st
    assert st["vendor_ready"] is False
