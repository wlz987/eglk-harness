from eglk_harness.domain.metering import tokens_and_cost_from_codex_jsonl


def test_meter_turn_completed():
    raw = (
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5},'
        '"total_cost_usd":0.02}\n'
    )
    tokens, cost = tokens_and_cost_from_codex_jsonl(raw)
    assert tokens == 15
    assert abs(cost - 0.02) < 1e-9


def test_meter_absent():
    assert tokens_and_cost_from_codex_jsonl("") == (0, 0.0)
