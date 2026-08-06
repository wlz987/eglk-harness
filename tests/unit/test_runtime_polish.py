"""Runtime polish: redact, format repair, model downgrade."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.runtime.format_repair import run_with_format_repair
from eglk_harness.domain.runtime.models import (
    get_active_downgrade,
    plan_model_downgrade,
    resolve_model,
    set_active_downgrade,
)
from eglk_harness.domain.runtime.redact import redact_secrets


def test_redact_secrets_masks_keys() -> None:
    raw = "OPENAI_API_KEY=sk-secret-value EGLK_API_KEY=abc --api-key xyz"
    out = redact_secrets(raw)
    assert "sk-secret-value" not in out
    assert "***REDACTED***" in out


def test_plan_model_downgrade_respects_never_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EGLK_MODEL_DOWNGRADE_THRESHOLD_USD", "1.0")
    monkeypatch.setenv("EGLK_MODEL_DOWNGRADE_VERIFIER", "cheap-v")
    monkeypatch.setenv("EGLK_MODEL_DOWNGRADE_REFINER", "cheap-r")
    plan = plan_model_downgrade(usd_used=2.0)
    assert plan["active"] is True
    assert plan["roles"]["verifier"] == "cheap-v"
    assert "maker" not in plan["roles"]
    set_active_downgrade(plan["roles"])
    assert resolve_model("verifier") == "cheap-v"
    monkeypatch.setenv("EGLK_MODEL_MAKER", "opus")
    assert resolve_model("maker") == "opus"  # never downgraded
    set_active_downgrade({})
    assert get_active_downgrade() == {}


@pytest.mark.asyncio
async def test_format_repair_retries_once(tmp_path: Path) -> None:
    class Flaky:
        name = "flaky"

        def __init__(self) -> None:
            self.calls = 0

        async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
            self.calls += 1
            if self.calls == 1:
                return EpisodeResult(ok=False, text="not json", error="unparseable:x", backend=self.name)
            claim = {
                "claim_id": "c1",
                "tick": 0,
                "maker_session_id": "m",
                "kind": "files",
                "done_progress": 1.0,
                "confidence": 0.9,
                "alternatives": [{"text": "a", "status": "reject", "reason": "x"}],
                "payload": {"files": {"a.txt": "hi"}},
                "step_review": {
                    "gains": ["g"],
                    "losses": ["l"],
                    "benefits": ["b"],
                    "risks": ["r"],
                },
                "shortcut_hit": False,
                "subgoal_id": "root",
            }
            return EpisodeResult(ok=True, text="{}", parsed=claim, backend=self.name)

    adapter = Flaky()
    req = EpisodeRequest(
        role="maker",
        prompt="go",
        workdir=tmp_path,
        tools_allowed=True,
        expect="claim",
    )
    result = await run_with_format_repair(adapter, req, leaf_block="[LEAF]")
    assert result.ok and isinstance(result.parsed, dict)
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_format_repair_retries_twice(tmp_path: Path) -> None:
    class TwiceFlaky:
        name = "twice"

        def __init__(self) -> None:
            self.calls = 0

        async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
            self.calls += 1
            if self.calls < 3:
                return EpisodeResult(ok=False, text="still bad", error="unparseable:y", backend=self.name)
            claim = {
                "claim_id": "c2",
                "tick": 0,
                "maker_session_id": "m",
                "kind": "files",
                "done_progress": 1.0,
                "confidence": 0.9,
                "alternatives": ["none"],
                "payload": {},
                "step_review": {
                    "gains": ["g"],
                    "losses": ["l"],
                    "benefits": ["b"],
                    "risks": ["r"],
                },
            }
            return EpisodeResult(ok=True, text="{}", parsed=claim, backend=self.name)

    adapter = TwiceFlaky()
    req = EpisodeRequest(
        role="maker",
        prompt="go",
        workdir=tmp_path,
        tools_allowed=True,
        expect="claim",
    )
    result = await run_with_format_repair(adapter, req, leaf_block="[LEAF]", max_repairs=2)
    assert result.ok
    assert adapter.calls == 3


@pytest.mark.asyncio
async def test_format_repair_recovers_without_llm_when_coerce_works(tmp_path: Path) -> None:
    class Once:
        name = "once"
        calls = 0

        async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
            self.calls += 1
            # Missing ids / extras — coerce should salvage without a second LLM call
            text = (
                '{"kind":"files","payload":{"files":{"a.txt":"x"}},'
                '"thread_id":"t","alternatives":["n"],'
                '"step_review":{"gains":["g"],"losses":["l"],"benefits":["b"],"risks":["r"]}}'
            )
            return EpisodeResult(ok=False, text=text, error="unparseable:missing", backend=self.name)

    adapter = Once()
    req = EpisodeRequest(
        role="maker",
        prompt="go",
        workdir=tmp_path,
        tools_allowed=True,
        expect="claim",
    )
    result = await run_with_format_repair(adapter, req, leaf_block="[LEAF]")
    assert result.ok and result.parsed and result.parsed["kind"] == "files"
    assert adapter.calls == 1
