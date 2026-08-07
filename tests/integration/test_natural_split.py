"""Natural split: no pre-split children; repair streak triggers Governor split."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.app import RunRequest, run
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.goal_parse import done_criteria, goal_id, read_goal_text, title_from_goal
from eglk_harness.domain.kernel.tree import make_root
from eglk_harness.domain.product.init_project import init_project


class IntegrityStreakThenAdmit(MockAdapter):
    def __init__(self) -> None:
        super().__init__(mode="repair_integrity")
        self._maker_checker = 0

    async def run_episode(self, request):  # type: ignore[no-untyped-def]
        if request.role in {"maker", "checker"} or request.expect in {"claim", "evidence"}:
            self._maker_checker += 1
            if self._maker_checker > 4:
                self.mode = "admit"
        return await super().run_episode(request)


def test_natural_split_without_presplit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Start as a single leaf (no children); streak → Governor split — never hand-written kids."""
    init_project(tmp_path)
    (tmp_path / ".goal.md").write_text(
        "# Natural\n\n"
        "- [ ] Write `a.txt` with A\n"
        "- [ ] Write `b.txt` with B\n"
        "- [ ] Write `c.txt` with C\n",
        encoding="utf-8",
    )

    text = read_goal_text(tmp_path)
    gid = goal_id(text)
    loop = loop_store.ensure_loop_layout(tmp_path, gid)
    tree0 = make_root(title_from_goal(text), done_criteria(text), leaf=True)
    loop_store.save_tree(loop, tree0)
    assert tree0.root.children == [], "must not start with a pre-split tree"

    import eglk_harness.app as app_mod

    monkeypatch.setattr(app_mod, "create_adapter", lambda *a, **k: IntegrityStreakThenAdmit())

    code = run(
        RunRequest(
            workdir=tmp_path,
            agent="mock",
            swarm="1",
            uncertainty=0.9,
            compile="off",
            max_ticks=12,
        )
    )
    assert code == 0
    tree = loop_store.load_tree(paths.loop_goal_dir(tmp_path, gid))
    assert tree is not None
    assert len(tree.root.children) >= 2
    assert tree.root.status == "split" or all(
        c.status in {"admitted", "pending", "in_progress", "merged"} for c in tree.root.children
    )
