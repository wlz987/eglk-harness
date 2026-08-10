"""WA-Hard hint must not leak Oracle answers into Maker/Checker surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eglk_harness.domain.eval.loader import load_suite_module

from tests.conftest import default_eval_root

EVAL_ROOT = default_eval_root()
HARNESS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "wa_scorer_export_minimal.json"


@pytest.mark.skipif(not EVAL_ROOT.is_dir(), reason="experiment/eval not present")
def test_agent_response_hint_uses_schema_placeholders_not_oracle(monkeypatch: pytest.MonkeyPatch) -> None:
    wa = load_suite_module("wa_hard", EVAL_ROOT)
    monkeypatch.setattr(wa, "scorer_export_path", lambda _root: HARNESS_FIXTURE)

    hint_31 = wa.agent_response_hint(EVAL_ROOT, "31")
    assert hint_31 is not None
    example = hint_31["example_success"]
    assert example.get("_placeholder") is True
    data = json.dumps(example.get("retrieved_data"))
    assert "Proud_Idiot" not in data
    assert "Rishi Sunak" not in data
    assert "note" in hint_31

    hint_11 = wa.agent_response_hint(EVAL_ROOT, "11")
    assert hint_11 is not None
    oracle = wa.load_scorer_export_index(EVAL_ROOT)["11"]["eval"][0]["expected"]["retrieved_data"]
    placeholder = hint_11["example_success"]["retrieved_data"]
    assert placeholder != oracle


def test_schema_placeholder_object_shape() -> None:
    wa = load_suite_module("wa_hard", EVAL_ROOT)
    out = wa.schema_placeholder_retrieved_data(
        {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"username": {"type": "string"}, "count": {"type": "number"}},
            },
        },
        task_type="RETRIEVE",
    )
    assert out == [{"username": "", "count": 0}]
