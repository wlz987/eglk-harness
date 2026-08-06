"""Message shape helpers (structural only; no gate / tree rules)."""

from __future__ import annotations

from typing import Any


def ok_body(**fields: Any) -> dict[str, Any]:
    return {"ok": True, **fields}


def err_body(error: str, **fields: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, **fields}
