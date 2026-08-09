"""Message shape helpers (structural only; no gate / tree rules)."""

from __future__ import annotations

from typing import Any


def ok_value(**fields: Any) -> dict[str, Any]:
    """Worker ``work()`` success payload — wrapped by eba as ``{"ok": true, "value": ...}``."""
    return dict(fields)


def work_error(error: str) -> None:
    """Raise a worker-visible failure (eba maps to ErrBody)."""
    raise ValueError(error)
