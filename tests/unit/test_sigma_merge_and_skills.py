"""Σ merge suggestions + LEARNED SKILLS matching."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.init_project import init_project
from eglk_harness.domain import skill_lib, sigma
from eglk_harness.domain.sigma_merge import suggest_sibling_merges, text_similarity
from eglk_harness.domain.tree import TaskTree


def test_text_similarity_overlap() -> None:
    assert text_similarity("keyword token regex", "literal token regex") > 0.3


def test_suggest_sibling_merges_from_sigma() -> None:
    tree = TaskTree.from_document(
        {
            "subgoals_tree": {
                "id": "root",
                "title": "g",
                "status": "pending",
                "done_criteria": ["all"],
                "children": [
                    {
                        "id": "sg_a",
                        "title": "kw",
                        "status": "pending",
                        "done_criteria": ["keyword token done"],
                        "children": [],
                        "parent_id": "root",
                    },
                    {
                        "id": "sg_b",
                        "title": "lit",
                        "status": "pending",
                        "done_criteria": ["literal token done"],
                        "children": [],
                        "parent_id": "root",
                    },
                ],
                "parent_id": None,
            }
        }
    )
    active = [
        {"id": "s1", "leaf_id": "sg_a", "cond": "avoid regex for keyword token", "text": "use tables"},
        {"id": "s2", "leaf_id": "sg_b", "cond": "avoid regex for literal token", "text": "use tables"},
    ]
    sug = suggest_sibling_merges(tree, active, min_sim=0.3)
    assert sug
    assert set(sug[0]["nodes"]) == {"sg_a", "sg_b"}


def test_match_and_render_learned_skills(tmp_path: Path) -> None:
    init_project(tmp_path)
    skill_lib.record_admit(tmp_path, leaf_id="root", title="write hello file", tick=0)
    matched = skill_lib.match_skills(tmp_path, leaf_id="root", title="write hello file")
    assert matched
    block = skill_lib.render_learned_skills_block(matched)
    assert "[LEARNED SKILLS]" in block
    assert "leaf:root" in block
