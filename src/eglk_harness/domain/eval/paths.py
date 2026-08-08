"""Resolve auxiliary eval asset roots (pack indices, fixtures — not live vendor trees)."""

from __future__ import annotations

import os
from pathlib import Path

_SUITE_DIRS = frozenset({"wa_hard", "weave_lh", "weave_thin", "osworld_aux", "tb21"})


def _looks_like_eval_root(path: Path) -> bool:
    return any((path / name).is_dir() for name in _SUITE_DIRS)


def bundled_eval_root() -> Path | None:
    """Packaged example indices shipped with eglk-harness."""
    here = Path(__file__).resolve()
    cand = here.parent / "bundled_eval"
    if cand.is_dir() and _looks_like_eval_root(cand):
        return cand
    return None


def default_eval_root() -> Path | None:
    """``EGLK_EVAL_ROOT`` when set, else packaged ``bundled_eval``."""
    raw = os.environ.get("EGLK_EVAL_ROOT", "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
    return bundled_eval_root()


def vendor_dir(eval_root: Path | None = None) -> Path | None:
    """Optional ``vendor/`` tree under the eval root (operator-provided harnesses)."""
    root = Path(eval_root).resolve() if eval_root is not None else default_eval_root()
    if root is None:
        return None
    cand = root / "vendor"
    return cand if cand.is_dir() else None
