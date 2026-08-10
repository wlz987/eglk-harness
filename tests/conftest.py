"""Shared pytest paths for eglk-harness + monorepo experiment/eval."""

from __future__ import annotations

import os
from pathlib import Path

_HARNESS_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _HARNESS_ROOT.parent
_DEFAULT_EVAL = _WORKSPACE_ROOT / "experiment" / "eval"

if not os.environ.get("EGLK_EVAL_ROOT") and _DEFAULT_EVAL.is_dir():
    os.environ["EGLK_EVAL_ROOT"] = str(_DEFAULT_EVAL.resolve())


def default_eval_root() -> Path:
    raw = (os.environ.get("EGLK_EVAL_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if _DEFAULT_EVAL.is_dir():
        return _DEFAULT_EVAL.resolve()
    return _DEFAULT_EVAL
