"""Bypass LLM soak — mock-forced path always; live gated by EGLK_SOAK_LIVE."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from eglk_harness.domain.adapters import MockAdapter
from eglk_harness.domain.adapters.factory import create_adapter
from eglk_harness.domain.eval.bypass_soak import soak_bypass_roles


@pytest.mark.asyncio
async def test_soak_bypass_mock_all_roles_llm(tmp_path: Path) -> None:
    adapter = MockAdapter()
    report = await soak_bypass_roles(adapter, tmp_path, force=True, timeout_s=30.0)
    assert report.ok
    assert {r.role for r in report.roles} >= {"governor", "explorer", "verifier", "refiner", "compile"}
    # Mock with force must produce llm sources for scripted bypass roles
    llm = [r for r in report.roles if r.source == "llm"]
    assert len(llm) >= 4
    assert (tmp_path / ".eglk-harness" / "soak" / "bypass" / "report.json").is_file()


@pytest.mark.asyncio
async def test_soak_bypass_live_optional(tmp_path: Path) -> None:
    if (os.environ.get("EGLK_SOAK_LIVE") or "").strip().lower() not in {"1", "on", "true", "yes"}:
        pytest.skip("set EGLK_SOAK_LIVE=1 with Codex/Claude available")
    agent = (os.environ.get("EGLK_SOAK_AGENT") or "codex").strip()
    adapter = create_adapter(agent)
    report = await soak_bypass_roles(adapter, tmp_path, force=True, timeout_s=180.0)
    assert report.ok
    assert any(r.source == "llm" for r in report.roles)
