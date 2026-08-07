"""Regression: live Claim/Evidence parse failures must recover via coerce."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.kernel.schema_validate import parse_and_validate
from eglk_harness.domain.runtime.json_extract import extract_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live_parse"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_prefer_last_agent_message_claim() -> None:
    doc, errs = parse_and_validate("claim", _load("prefer_last_message.txt"))
    assert errs == [], errs
    assert doc is not None
    assert doc["claim_id"] == "last"


def test_array_wrapped_claim_unwraps() -> None:
    doc, errs = parse_and_validate("claim", _load("bookmark_array_wrap.txt"))
    assert errs == [], errs
    assert doc is not None
    assert doc["claim_id"] == "bk-1"


def test_strip_extras_and_alt_tick_fixture() -> None:
    doc, errs = parse_and_validate("claim", _load("toy_hello2_alt_tick.txt"))
    assert errs == [], errs
    assert doc is not None
    assert "thread_id" not in doc
    assert "type" not in doc
    assert doc["tick"] == 0
    assert doc["alternatives"][0]["text"] == "alt_print_to_stdout"


def test_partial_claim_fills_safe_defaults() -> None:
    doc, errs = parse_and_validate("claim", _load("toy_hello_partial_claim.txt"))
    assert errs == [], errs
    assert doc is not None
    assert doc["kind"] == "files"
    assert doc["payload"]["files"]["hello.txt"] == "hello from eglk"
    assert doc["claim_id"]
    assert doc["maker_session_id"]
    assert doc["done_progress"] == 0.0
    assert doc["confidence"] == 0.0
    assert "thread_id" not in doc


def test_codex_noise_without_domain_object_still_errors_or_recovers() -> None:
    """Pure protocol noise may fail; must not crash. Prefer domain if any."""
    text = _load("toy_hello_codex_noise.txt")
    try:
        raw = extract_json(text)
    except ValueError:
        return
    assert isinstance(raw, dict)
    # If something was extracted, it must not be a bare protocol envelope preferred as claim
    doc, errs = parse_and_validate("claim", text)
    if errs:
        assert "thread_id" not in (doc or {})
        return
    assert doc is not None
    assert "claim_id" in doc


def test_sparse_evidence_fills_defaults() -> None:
    doc, errs = parse_and_validate("evidence", _load("evidence_sparse.txt"))
    assert errs == [], errs
    assert doc is not None
    assert doc["evidence_id"]
    assert doc["checker_session_id"]
    assert doc["audit_progress"] == 0.0
    assert isinstance(doc["artifacts"], list)
    assert all(isinstance(x, str) for x in doc["artifacts"])
    assert "thread_id" not in doc


def test_claim_emitted_via_shell_cat_in_codex_jsonl() -> None:
    """Live failure mode: Claim only in command_execution stdout, prose in agent_message."""
    from eglk_harness.domain.adapters.base import EpisodeRequest
    from eglk_harness.domain.adapters.parse import episode_from_text

    raw = _load("claim_via_shell_cat.txt")
    doc, errs = parse_and_validate("claim", raw)
    assert errs == [], errs
    assert doc is not None
    assert doc["claim_id"] == "c-root-0"
    req = EpisodeRequest(
        role="maker",
        prompt="x",
        workdir=Path("."),
        tools_allowed=True,
        expect="claim",
    )
    res = episode_from_text(req, raw, backend="codex")
    assert res.ok and res.parsed is not None
    assert res.parsed["claim_id"] == "c-root-0"
