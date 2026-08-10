"""WA-Hard hint must not leak Oracle answers into Maker/Checker surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eglk_harness.domain.eval.loader import load_suite_module

EVAL_ROOT = Path(__file__).resolve().parents[2] / "experiment" / "eval"
FIXTURE = EVAL_ROOT / "wa_hard" / "fixtures" / "webarena-verified-hard.export.json"


@pytest.mark.skipif(not FIXTURE.is_file(), reason="experiment/eval fixtures not present")
def test_agent_response_hint_uses_schema_placeholders_not_oracle() -> None:
    wa = load_suite_module("wa_hard", EVAL_ROOT)
    hint_31 = wa.agent_response_hint(EVAL_ROOT, "31")
    assert hint_31 is not None
    example = hint_31["example_success"]
    assert example.get("_placeholder") is True
    data = json.dumps(example.get("retrieved_data"))
    assert "Proud_Idiot" not in data
    assert "Rishi Sunak" not in data
    assert hint_31.get("retrieval_guidance")

    hint_11 = wa.agent_response_hint(EVAL_ROOT, "11")
    assert hint_11 is not None
    # Oracle count for task 11 should not appear in placeholder
    oracle = wa.load_export_index(EVAL_ROOT)["11"]["eval"][0]["expected"]["retrieved_data"]
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
