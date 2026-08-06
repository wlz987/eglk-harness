"""Control-kernel hardening: tokens, compile, governor split, skill_lib, repair_counts."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.adapters.base import EpisodeRequest
from eglk_harness.domain.adapters.parse import episode_from_text
from eglk_harness.domain.compile_goal import compile_goal, format_goal_frame
from eglk_harness.domain.governor_split import propose_children
from eglk_harness.domain.repair_counts import repair_counts_from_decisions
from eglk_harness.domain import skill_lib, sigma
from eglk_harness.domain.tokens import add_tokens, tokens_from_codex_jsonl, update_focus_uncertainty
from eglk_harness.actors.swarm import explore_alternatives


def test_tokens_from_codex_jsonl_prefers_total() -> None:
    stream = (
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":3}}\n'
    )
    assert tokens_from_codex_jsonl(stream) == 20  # 15 + (2+3)


def test_episode_from_text_meters_tokens() -> None:
    stream = (
        '{"type":"item.completed","item":{"id":"item_1","type":"agent_message",'
        '"text":"```json\\n{\\"claim_id\\":\\"c1\\",\\"tick\\":0,\\"maker_session_id\\":\\"m\\",'
        '\\"kind\\":\\"files\\",\\"done_progress\\":1.0,\\"confidence\\":0.9,'
        '\\"alternatives\\":[{\\"text\\":\\"alt\\",\\"status\\":\\"reject\\"}],'
        '\\"payload\\":{\\"files\\":{\\"a.txt\\":\\"x\\"}},'
        '\\"step_review\\":{\\"gains\\":[\\"g\\"],\\"losses\\":[\\"l\\"],'
        '\\"benefits\\":[\\"b\\"],\\"risks\\":[\\"r\\"]}}\\n```"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":20}}\n'
    )
    ep = episode_from_text(
        EpisodeRequest(
            role="maker",
            prompt="x",
            workdir=Path("."),
            tools_allowed=True,
            expect="claim",
        ),
        stream,
        backend="codex",
    )
    assert ep.ok and ep.tokens == 120


def test_format_goal_frame_extracts_sections() -> None:
    goal = """# Bookmark CLI

## Acceptance
- store saves URLs
- CLI lists bookmarks

## Constraints
- no network
"""
    text = format_goal_frame(goal)
    assert "store saves URLs" in text
    assert "no network" in text
    assert "No concrete subtask split" in text


def test_compile_writes_rich_frame(tmp_path: Path) -> None:
    (tmp_path / ".goal.md").write_text(
        "# Demo\n\n## Acceptance\n- a.txt exists\n",
        encoding="utf-8",
    )
    r = compile_goal(tmp_path, mode="force", backend="mock")
    assert r.action == "wrote"
    body = (tmp_path / ".goal_format.md").read_text(encoding="utf-8")
    assert "a.txt exists" in body
    assert "## Acceptance (abstract)" in body


def test_propose_children_from_criteria() -> None:
    kids = propose_children("root", "Build X", ["crit A", "crit B", "crit C"])
    assert len(kids) == 3
    assert kids[0]["done_criteria"] == ["crit A"]
    assert "part A done" not in json.dumps(kids)

    single = propose_children("leaf", "One", ["only"])
    assert len(single) == 2
    assert "Implement" in single[0]["title"]
    assert "Verify" in single[1]["title"]


def test_explore_alternatives_leaf_aware() -> None:
    alts = explore_alternatives("Ship form", ["png evidence", "submit ok"])
    texts = " ".join(a["text"] for a in alts)
    assert "png evidence" in texts
    assert any(a["id"] == "alt-low-value" for a in alts)


def test_skill_lib_record_and_hints(tmp_path: Path) -> None:
    from eglk_harness.domain.init_project import init_project

    init_project(tmp_path)
    skill_lib.record_admit(
        tmp_path,
        leaf_id="root",
        title="Hello",
        tick=0,
        claim={"step_review": {"benefits": ["wrote hello"]}},
    )
    items = skill_lib.load_index(tmp_path)
    assert items and items[0]["usage_count"] == 1
    hints = skill_lib.boundary_hints(tmp_path, leaf_id="root", title="Hello")
    assert hints


def test_repair_counts_and_focus(tmp_path: Path) -> None:
    dec = tmp_path / "decisions"
    dec.mkdir()
    (dec / "000.json").write_text(
        json.dumps({"decision": "repair", "reason": "incomplete", "subgoal_id": "root"}),
        encoding="utf-8",
    )
    (dec / "001.json").write_text(
        json.dumps({"decision": "repair", "reason": "incomplete", "subgoal_id": "root"}),
        encoding="utf-8",
    )
    assert repair_counts_from_decisions(tmp_path, subgoal_id="root")["incomplete"] == 2
    f, u = update_focus_uncertainty(decision="repair", focus_score=1.0, uncertainty=0.0)
    assert f < 1.0 and u > 0.0
    q = add_tokens({"cognitive_tokens": 10}, 5)
    assert q["cognitive_tokens"] == 15


def test_sigma_merge_dedupes(tmp_path: Path) -> None:
    from eglk_harness.domain.init_project import init_project
    from eglk_harness.domain import paths

    init_project(tmp_path)
    loop = paths.loop_goal_dir(tmp_path, "g1")
    (loop / "sigma" / "refined").mkdir(parents=True)
    (loop / "sigma" / "refined" / "000.json").write_text(
        json.dumps({"id": "sigma-hit-000", "kind": "hit", "text": "a"}),
        encoding="utf-8",
    )
    (loop / "sigma" / "refined" / "001.json").write_text(
        json.dumps({"id": "sigma-hit-000", "kind": "hit", "text": "c"}),
        encoding="utf-8",
    )
    n = sigma.merge_refined_into_active(tmp_path, loop)
    assert n == 2
    active = sigma.load_active(tmp_path)
    ids = [x.get("id") for x in active]
    assert ids.count("sigma-hit-000") == 1
    assert any(x.get("text") == "c" for x in active)
