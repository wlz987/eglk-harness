from eglk_harness.domain.runtime.metering import tokens_and_cost_from_codex_jsonl


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


def test_meter_ignores_cached_input_double_count():
    raw = (
        '{"type":"turn.completed","usage":{'
        '"input_tokens":100,"cached_input_tokens":80,"output_tokens":5}}\n'
    )
    tokens, _ = tokens_and_cost_from_codex_jsonl(raw)
    assert tokens == 105
