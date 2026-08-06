from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.tree import TaskTree, make_root


def test_admit_advances_next_leaf() -> None:
    tree = TaskTree.from_document(
        {
            "subgoals_tree": {
                "id": "root",
                "title": "goal",
                "status": "pending",
                "done_criteria": ["all"],
                "children": [
                    {
                        "id": "sg_01",
                        "title": "a",
                        "status": "in_progress",
                        "done_criteria": ["a ok"],
                        "children": [],
                        "parent_id": "root",
                    },
                    {
                        "id": "sg_02",
                        "title": "b",
                        "status": "pending",
                        "done_criteria": ["b ok"],
                        "children": [],
                        "parent_id": "root",
                    },
                ],
                "parent_id": None,
            }
        }
    )
    admitted = tree.admit_current()
    assert admitted is not None and admitted.id == "sg_01"
    assert admitted.status == "admitted"
    nxt = tree.in_progress()
    assert nxt is not None and nxt.id == "sg_02"


def test_repair_increments_streak_and_should_split() -> None:
    tree = make_root("g", ["done"])
    assert tree.should_split() is False
    tree.repair_current()
    tree.ensure_pointer()
    assert tree.in_progress() is not None
    assert tree.in_progress().repair_streak == 1
    assert tree.should_split() is False
    tree.repair_current()
    tree.ensure_pointer()
    assert tree.in_progress().repair_streak == 2
    assert tree.should_split() is True


def test_split_creates_children() -> None:
    tree = make_root("g", ["done"])
    tree.repair_current()
    tree.ensure_pointer()
    tree.repair_current()
    node = tree.find("root")
    assert node is not None
    tree.split_node(
        "root",
        [
            {"id": "sg_01", "title": "p1", "done_criteria": ["c1"]},
            {"id": "sg_02", "title": "p2", "done_criteria": ["c2"]},
        ],
    )
    assert tree.find("root").status == "split"
    assert tree.in_progress().id == "sg_01"
    assert tree.find("sg_02").status == "pending"


def test_max_split_depth() -> None:
    tree = make_root("g", ["done"])
    # artificially deep chain
    n = tree.root
    for i in range(P.MAX_SPLIT_DEPTH):
        child_id = f"sg_{i}"
        from eglk_harness.domain.kernel.tree import TreeNode

        child = TreeNode(
            id=child_id,
            title=child_id,
            status="in_progress",
            done_criteria=["x"],
            parent_id=n.id,
        )
        n.status = "split"
        n.children = [child]
        # clear other in_progress
        for x, _ in tree.walk():
            if x.id != child_id and x.status == "in_progress":
                x.status = "pending"
        n = child
    deep = tree.in_progress()
    assert deep is not None
    deep.repair_streak = P.SPLIT_REPAIR_STREAK
    assert tree.should_split(deep) is False


def test_all_work_admitted() -> None:
    tree = make_root("g", ["done"])
    assert tree.all_work_admitted() is False
    tree.admit_current()
    assert tree.all_work_admitted() is True
    assert tree.root.status == "admitted"


def test_fail_current() -> None:
    tree = make_root("g", ["done"])
    tree.fail_current()
    assert tree.root.status == "failed"


def test_try_merge_siblings_after_admit() -> None:
    tree = TaskTree.from_document(
        {
            "subgoals_tree": {
                "id": "root",
                "title": "goal",
                "status": "pending",
                "done_criteria": ["all"],
                "children": [
                    {
                        "id": "sg_01",
                        "title": "a",
                        "status": "in_progress",
                        "done_criteria": ["shared token rule", "a-only"],
                        "children": [],
                        "parent_id": "root",
                    },
                    {
                        "id": "sg_02",
                        "title": "b",
                        "status": "pending",
                        "done_criteria": ["shared token rule", "b-only"],
                        "children": [],
                        "parent_id": "root",
                    },
                    {
                        "id": "sg_03",
                        "title": "c",
                        "status": "pending",
                        "done_criteria": ["unrelated"],
                        "children": [],
                        "parent_id": "root",
                    },
                ],
                "parent_id": None,
            }
        }
    )
    tree.admit_current()
    ev = tree.try_merge_siblings_after_admit("sg_01")
    assert ev is not None
    assert ev["nodes"] == ["sg_02"]
    assert tree.find("sg_01").status == "admitted"
    assert tree.find("sg_02").status == "merged"
    assert tree.find("sg_03").status in {"pending", "in_progress"}
    merged = tree.find(ev["into"])
    assert merged is not None and merged.status in {"pending", "in_progress"}
    assert "shared token rule" in merged.done_criteria
    assert "b-only" in merged.done_criteria
    assert tree.in_progress() is not None
