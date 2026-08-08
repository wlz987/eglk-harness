"""Tests for WA-Hard subset pack builder / dry-run helpers."""

from __future__ import annotations

import json
from pathlib import Path

from eglk_harness.domain.eval import wa_hard as wa
from tests.helpers.eval_root import eval_root_for_tests


def test_build_pack_from_subset_prefers_phase0(tmp_path: Path) -> None:
    subset = tmp_path / "hard.json"
    subset.write_text(
        json.dumps(
            [
                {"task_id": 11, "intent": "a", "sites": ["shopping_admin"], "intent_template_id": 1},
                {"task_id": 681, "intent": "phase0-a", "sites": ["reddit"], "intent_template_id": 2},
                {"task_id": 522, "intent": "phase0-b", "sites": ["gitlab"], "intent_template_id": 3},
                {"task_id": 21, "intent": "c", "sites": ["shopping"], "intent_template_id": 4},
            ]
        ),
        encoding="utf-8",
    )
    pack = wa.build_pack_from_subset(subset, limit=3)
    ids = [t["id"] for t in pack["tasks"]]
    assert ids[0] == "681"
    assert ids[1] == "522"
    assert len(ids) == 3


def test_write_pack(tmp_path: Path) -> None:
    pack = {
        "pack": "wa_verified_hard",
        "tasks": [{"id": "681", "intent": "x", "sites": ["reddit"], "notes": ""}],
    }
    path = wa.write_pack(tmp_path, pack)
    assert path.is_file()
    loaded = wa.load_pack_index(tmp_path)
    assert loaded[0].task_id == "681"


def test_official_pack_has_phase0_ids() -> None:
    eval_root = eval_root_for_tests()
    ids = {t.task_id for t in wa.load_pack_index(eval_root)}
    assert "681" in ids
    assert "522" in ids
