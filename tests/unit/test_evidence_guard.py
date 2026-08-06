from eglk_harness.domain.evidence_guard import normalize_evidence


def test_strips_oracle_keys():
    raw = {
        "passed": True,
        "gaps": [],
        "artifacts": ["a.txt"],
        "pass_rate": 0.9,
        "oracle": True,
        "score": 1,
    }
    out = normalize_evidence(raw, written=["a.txt"])
    assert "pass_rate" not in out
    assert "oracle" not in out
    assert "score" not in out
    assert out["passed"] is True
    assert out["artifacts"] == ["a.txt"]


def test_fills_empty_gaps_and_artifacts_from_written():
    out = normalize_evidence({"passed": False}, written=["x.py"])
    assert out["gaps"] == []
    assert out["artifacts"] == ["x.py"]
