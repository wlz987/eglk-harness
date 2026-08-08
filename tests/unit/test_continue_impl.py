"""Continuation: provider overrides, K distill, wa_hard, environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain.adapters.codex_overrides import provider_overrides
from eglk_harness.domain.adapters.agent_logs import visible_output
from eglk_harness.domain.environment.local import LocalEnvironment
from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.memory import skill_lib
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.eval import wa_hard as wa_hard_mod
from tests.helpers.eval_root import eval_root_for_tests


def test_provider_overrides_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EGLK_BASE_URL", "http://127.0.0.1:28000/v1")
    monkeypatch.setenv("EGLK_API_KEY", "sk-test")
    ov = provider_overrides()
    assert any("model_providers.eglk_harness=" in x for x in ov)
    assert any("model_provider=" in x for x in ov)


def test_provider_overrides_key_alone_preserves_codex_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EGLK_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-vllm")
    assert provider_overrides() == []


def test_visible_output_codex_jsonl() -> None:
    stream = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"hello visible"}}\n'
    )
    assert "hello visible" in visible_output(stream)


def test_skill_distill_revise_deprecate(tmp_path: Path) -> None:
    init_project(tmp_path)
    sigma.save_active(
        tmp_path,
        [{"id": "sigma-hit-001", "kind": "hit", "text": "always write tests", "conf": 0.9}],
    )
    created = skill_lib.distill_from_sigma(tmp_path, min_conf=0.65)
    assert created and created[0]["id"] == "sigma:sigma-hit-001"
    active = sigma.load_active(tmp_path)
    assert active[0].get("distilled_into") == "sigma:sigma-hit-001"
    revised = skill_lib.revise_skill(tmp_path, "sigma:sigma-hit-001", note="add edge cases")
    assert revised and revised["version"] == 2
    dep = skill_lib.deprecate(tmp_path, "sigma:sigma-hit-001", reason="obsolete")
    assert dep and dep["status"] == "deprecated"


def test_wa_hard_materialize(tmp_path: Path) -> None:
    eval_root = eval_root_for_tests()
    tasks = wa_hard_mod.load_pack_index(eval_root)
    assert tasks
    goal = wa_hard_mod.materialize_goal(tasks[0], tmp_path)
    assert goal.is_file() and "WA-Hard" in goal.read_text(encoding="utf-8")
    scores = wa_hard_mod.score_placeholder(task_id=tasks[0].task_id, workdir=tmp_path)
    assert scores["judge"] == "external_wa_verified"


def test_skill_deconstruct(tmp_path: Path) -> None:
    init_project(tmp_path)
    skill_lib.record_admit(tmp_path, leaf_id="root", title="root skill", tick=0)
    parts = skill_lib.deconstruct(tmp_path, "leaf:root", parts=["part A setup", "part B verify"])
    assert len(parts) == 2
    idx = skill_lib.load_index(tmp_path)
    parent = next(x for x in idx if x["id"] == "leaf:root")
    assert parent.get("children") == ["leaf:root.part1", "leaf:root.part2"]


def test_osworld_materialize(tmp_path: Path) -> None:
    from eglk_harness.domain.eval import osworld as osworld_mod

    eval_root = eval_root_for_tests()
    tasks = osworld_mod.load_pack_index(eval_root)
    assert tasks
    goal = osworld_mod.materialize_goal(tasks[0], tmp_path)
    assert goal.is_file() and "OSWorld" in goal.read_text(encoding="utf-8")
    scores = osworld_mod.score_placeholder(task_id=tasks[0].task_id, workdir=tmp_path)
    assert scores["judge"] == "external_osworld"


@pytest.mark.asyncio
async def test_bypass_llm_auto_skips_mock() -> None:
    from eglk_harness.domain.adapters import MockAdapter
    from eglk_harness.domain.runtime.bypass_llm import bypass_llm_enabled, run_bypass_json

    adapter = MockAdapter()
    assert bypass_llm_enabled(adapter) is False
    raw = await run_bypass_json(
        adapter,
        role="governor",
        workdir=Path("/tmp"),
        leaf_block="[LEAF]\nid: root",
    )
    assert raw is None
    forced = await run_bypass_json(
        adapter,
        role="governor",
        workdir=Path("/tmp"),
        leaf_block="[LEAF]\nid: root",
        force=True,
    )
    assert forced and forced.get("children")


def test_context_compress_tick_signals() -> None:
    from eglk_harness.domain.memory.context_compress import compress_tick_signals

    out = compress_tick_signals(
        decision="admit",
        focus_score=1.0,
        uncertainty=0.0,
        cognitive_tokens=100,
        candidate_count=0,
    )
    assert "next_swarm" in out
    assert out["focus_score"] <= 1.0


@pytest.mark.asyncio
async def test_local_env_timeout_kills() -> None:
    env = LocalEnvironment()
    with pytest.raises(TimeoutError):
        await env.exec(["sleep", "30"], timeout_s=0.2)
