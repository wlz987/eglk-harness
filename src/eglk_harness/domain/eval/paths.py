"""Resolve auxiliary eval asset roots (pack indices, fixtures — not live vendor trees)."""

from __future__ import annotations

import os
from pathlib import Path

_SUITE_DIRS = frozenset({"wa_hard", "weave_lh", "weave_thin", "osworld_aux", "tb21"})


def _looks_like_eval_root(path: Path) -> bool:
    return any((path / name).is_dir() for name in _SUITE_DIRS)


def default_eval_root() -> Path | None:
    """``EGLK_EVAL_ROOT`` when set (e.g. ``experiment/eval``)."""
    raw = os.environ.get("EGLK_EVAL_ROOT", "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
    return None


def vendor_dir(eval_root: Path | None = None) -> Path | None:
    """Optional ``vendor/`` tree under the eval root (operator-provided harnesses)."""
    root = Path(eval_root).resolve() if eval_root is not None else default_eval_root()
    if root is None:
        return None
    cand = root / "vendor"
    return cand if cand.is_dir() else None
