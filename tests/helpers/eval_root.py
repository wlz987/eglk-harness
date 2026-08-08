"""Shared eval root for tests (bundled packs inside eglk-harness)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eglk_harness.domain.eval.paths import bundled_eval_root, default_eval_root


def eval_root_for_tests() -> Path:
    root = default_eval_root()
    if root is None:
        pytest.skip("bundled eval packs missing")
    return Path(root)


def bundled_wa_hard_fixtures() -> Path:
    root = bundled_eval_root()
    if root is None:
        pytest.skip("bundled eval packs missing")
    return root / "wa_hard" / "fixtures"
