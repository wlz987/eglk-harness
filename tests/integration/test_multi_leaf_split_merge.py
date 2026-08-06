"""Multi-leaf split → admit → structural merge."""

from __future__ import annotations

from eglk_harness.domain.tree import make_root


def test_structural_split_creates_children():
    tree = make_root("Do big thing", ["overall done"])
    children = [
        {"id": "sg_a", "title": "Part A", "done_criteria": ["a done"]},
        {"id": "sg_b", "title": "Part B", "done_criteria": ["b done"]},
    ]
    tree.split_node("root", children)
    root = tree.find("root")
    assert root is not None
    assert root.status == "split"
    assert len(root.children) >= 2
    assert {c.id for c in root.children} == {"sg_a", "sg_b"}


def test_admit_then_overlap_merge():
    tree = make_root("Parent work", ["ship all"])
    tree.split_node(
        "root",
        [
            {"id": "leaf_a", "title": "A", "done_criteria": ["shared crit", "a only"]},
            {"id": "leaf_b", "title": "B", "done_criteria": ["shared crit", "b only"]},
        ],
    )
    a = tree.find("leaf_a")
    assert a is not None
    a.status = "admitted"
    event = tree.try_merge_siblings_after_admit("leaf_a")
    assert event is not None
    assert event["event"] == "merge"
    assert "leaf_b" in event["nodes"]
    merged = tree.find(event["into"])
    assert merged is not None
    assert merged.status in {"pending", "in_progress"}
    assert any("shared" in c.lower() for c in merged.done_criteria)
