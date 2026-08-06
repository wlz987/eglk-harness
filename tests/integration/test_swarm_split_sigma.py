"""Integration: repair streak → Governor split → child admit → Σ merge."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.app import RunRequest, run
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.product.init_project import init_project


class IntegrityStreakThenAdmit(MockAdapter):
    """Two integrity-repair ticks build SPLIT_REPAIR_STREAK, then admit."""

    def __init__(self) -> None:
        super().__init__(mode="repair_integrity")
        self._maker_checker = 0

    async def run_episode(self, request):  # type: ignore[no-untyped-def]
        if request.role in {"maker", "checker"} or request.expect in {"claim", "evidence"}:
            self._maker_checker += 1
            # 2 ticks × (maker+checker) = 4 episodes of integrity repair
            if self._maker_checker > 4:
                self.mode = "admit"
        return await super().run_episode(request)


def test_repair_streak_splits_then_sigma_merges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_project(tmp_path)
    (tmp_path / ".goal.md").write_text(
        "# Split demo\n\n"
        "## Done criteria\n\n"
        "- [ ] Write `part_a.txt` with text A\n"
        "- [ ] Write `part_b.txt` with text B\n"
        "- [ ] Write `README.md` mentioning both parts\n",
        encoding="utf-8",
    )

    import eglk_harness.app as app_mod

    adapter = IntegrityStreakThenAdmit()
    monkeypatch.setattr(app_mod, "create_adapter", lambda *a, **k: adapter)

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

    loop_dirs = [p for p in paths.loop_root(tmp_path).iterdir() if p.is_dir()]
    assert loop_dirs
    loop = loop_dirs[0]
    tree = loop_store.load_tree(loop)
    assert tree is not None
    root = tree.find("root")
    assert root is not None
    assert root.status == "split" or (root.children and len(root.children) >= 2)
    assert len(root.children) >= 2

    # Phase3 Σ merge left durable active memory
    active = sigma.load_active(tmp_path)
    assert active, "expected sigma.active entries after admit+refine"

    # Gate never persisted explorer candidates as Gate inputs (files may exist under candidates/)
    decisions = sorted((loop / "decisions").glob("*.json"))
    assert len(decisions) >= 3
