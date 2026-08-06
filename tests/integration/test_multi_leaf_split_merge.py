"""Multi-leaf split under mock (bookmark shape, shrunk)."""

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
