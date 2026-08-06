"""Deep agent_logs: format detect, steps, runtime signals, sidecars."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.adapters.agent_logs import (
    detect_format,
    iter_steps,
    runtime_signal_labels,
    visible_output,
    write_trajectory_sidecars,
)

CODEX = '{"type":"item.completed","item":{"type":"agent_message","text":"hi"}}\n'
CLAUDE = '{"type":"assistant","message":{"content":[{"type":"text","text":"yo"}]}}\n'
CODEX_FAIL = '{"type":"turn.failed","error":{"message":"boom"}}\n'


def test_detect_codex():
    assert detect_format(CODEX) == "codex_exec_json"


def test_detect_claude():
    assert detect_format(CLAUDE) == "claude_stream_json"


def test_steps_and_visible():
    assert "hi" in visible_output(CODEX)
    steps = iter_steps(CODEX)
    assert any(s.get("kind") == "message" for s in steps)


def test_runtime_signal_labels_turn_failed():
    labels = runtime_signal_labels(CODEX_FAIL)
    assert "AGENT_TURN_FAILED" in labels


def test_write_sidecars(tmp_path: Path):
    tee = tmp_path / "maker_000.jsonl"
    tee.write_text(CODEX, encoding="utf-8")
    paths = write_trajectory_sidecars(str(tee), tee.read_text(encoding="utf-8"))
    assert Path(paths["visible"]).is_file()
    assert Path(paths["steps"]).is_file()
    assert "hi" in Path(paths["visible"]).read_text(encoding="utf-8")
