"""Skill frontmatter, progressive disclosure, goal-boundary verify (generic)."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.kernel.compile_goal import load_goal_constraints
from eglk_harness.domain.kernel.leaf_contract import contract_from_dict
from eglk_harness.domain.memory.skill_frontmatter import parse_skill_text
from eglk_harness.domain.memory.skills import (
    DisclosureLevel,
    load_skill,
    load_skill_metadata,
    render_prompt,
)
from eglk_harness.domain.runtime.boundary_verify import apply_boundary_to_evidence, verify_boundary


def test_skill_frontmatter_stripped_from_body() -> None:
    raw = load_skill("maker")
    assert "---" not in raw.splitlines()[0]
    assert "Maker" in raw
    meta = load_skill_metadata("maker")
    assert meta["name"] == "maker"
    assert meta["description"]


def test_render_prompt_core_vs_full() -> None:
    core = render_prompt("maker", leaf_block="[LEAF]", disclosure=DisclosureLevel.CORE)
    full = render_prompt("maker", leaf_block="[LEAF]", format_repair=True)
    assert "[SKILL maker]" in core
    assert "allowed-tools:" in core
    assert "copy shape exactly" in full
    assert "copy shape exactly" not in core or full.count("copy shape") > core.count("copy shape")


def test_boundary_verify_must_exist(tmp_path: Path) -> None:
    boundary = [
        "MUST_EXIST: out/result.json",
        "MUST_EXIST: out/trace.har",
    ]
    gaps = verify_boundary(tmp_path, boundary)
    assert any("result.json" in g for g in gaps)
    out = tmp_path / "out"
    out.mkdir()
    (out / "result.json").write_text('{"ok": true}\n', encoding="utf-8")
    (out / "trace.har").write_text(
        json.dumps({"log": {"version": "1.2", "entries": []}}) + "\n",
        encoding="utf-8",
    )
    assert verify_boundary(tmp_path, boundary) == []


def test_boundary_merges_into_evidence(tmp_path: Path) -> None:
    boundary = ["MUST_EXIST: missing/file.txt"]
    ev = apply_boundary_to_evidence(
        {"gaps": [], "artifacts": [], "audit_progress": 1.0},
        workdir=tmp_path,
        boundary=boundary,
    )
    assert ev["gaps"]
    assert ev["audit_progress"] < 1.0


def test_goal_constraints_from_goal_md(tmp_path: Path) -> None:
    (tmp_path / ".goal.md").write_text(
        "# G\n\n## Constraints\n\n- MUST_EXIST: foo.txt\n",
        encoding="utf-8",
    )
    cons = load_goal_constraints(tmp_path)
    assert any("foo.txt" in c for c in cons)


def test_contract_from_dict_boundary() -> None:
    lines = ["MUST_EXIST: artifacts/report.json"]
    lc = contract_from_dict(
        {
            "leaf_id": "root",
            "goal": "t",
            "acceptance": ["a"],
            "boundary": lines,
        }
    )
    assert "MUST_EXIST" in lc.render_maker_block()


def test_parse_skill_text_sections() -> None:
    text = (
        "---\nname: x\ndescription: d\n---\n\n"
        "# T\n\n## Hard rules\n\nrule\n\n## Example\n\nex\n"
    )
    doc = parse_skill_text("x", text)
    assert doc.description == "d"
    assert "Hard rules" in doc.sections
