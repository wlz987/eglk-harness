"""Read args / tool_args from envelopes (contract layer — not domain)."""

from __future__ import annotations

from typing import Any, Mapping


def get_args(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return the ``args`` object from an envelope payload, or ``{}``."""
    if not payload:
        return {}
    raw = payload.get("args")
    return dict(raw) if isinstance(raw, Mapping) else {}
