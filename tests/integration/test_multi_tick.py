"""Multi-tick run loop: repair → retry until admit or halt."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.app import RunRequest, run
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.kernel import paths


class FlipThenAdmitAdapter(MockAdapter):
    """First tick fails grounding; subsequent ticks admit."""

    def __init__(self) -> None:
        super().__init__(mode="repair_empty")
        self._episodes = 0

    async def run_episode(self, request):  # type: ignore[no-untyped-def]
        self._episodes += 1
        self.mode = "admit" if self._episodes > 2 else "repair_empty"
        return await super().run_episode(request)


def test_multi_tick_repair_then_admit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_project(tmp_path)
    (tmp_path / ".goal.md").write_text(
        "# Multi\n\n- [ ] hello.txt exists\n",
        encoding="utf-8",
    )

    import eglk_harness.app as app_mod

    monkeypatch.setattr(app_mod, "create_adapter", lambda *a, **k: FlipThenAdmitAdapter())

    code = run(
        RunRequest(
            workdir=tmp_path,
            agent="mock",
            swarm="0",
            compile="off",
            max_ticks=8,
        )
    )
    assert code == 0
    assert (tmp_path / "hello.txt").is_file()
    loop_dirs = [p for p in paths.loop_root(tmp_path).iterdir() if p.is_dir()]
    assert loop_dirs
    loop = loop_dirs[0]
    assert (loop / "decisions" / "000.json").is_file()
    assert (loop / "decisions" / "001.json").is_file()
    d0 = loop_store.read_json(loop / "decisions" / "000.json")
    d1 = loop_store.read_json(loop / "decisions" / "001.json")
    assert d0["decision"] == "repair"
    assert d1["decision"] == "admit"
