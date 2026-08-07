"""Explorer coerce must tolerate live LLM schema drift."""

from __future__ import annotations

from eglk_harness.domain.runtime.bypass_llm import coerce_explorer


def test_coerce_explorer_string_impact_and_name_fields() -> None:
    raw = {
        "alternatives": [
            {
                "id": "alt-1",
                "name": "Sequential writes",
                "description": "One agent writes all files",
                "impact": "Highest probability of correctness",
                "prob": "high",
            },
            {
                "id": "alt-2",
                "text": "parallel split",
                "impact": 0.9,
                "prob": 0.7,
            },
        ]
    }
    doc = coerce_explorer(raw, tick=0, leaf="root", fallback=[{"id": "f", "text": "fb", "prob": 0.1, "impact": 0.1}])
    assert doc["source"] == "llm"
    assert len(doc["alternatives"]) == 2
    assert "Sequential" in doc["alternatives"][0]["text"]
    assert 0.0 <= doc["alternatives"][0]["impact"] <= 1.0
    assert doc["alternatives"][1]["impact"] == 0.9
