"""Shared / per-role model resolution (economics lite — shared model first)."""

from __future__ import annotations

import os
from typing import Mapping

# Maker / Governor / Checker never downgrade (design/kernel/model_economics.md).
NEVER_DOWNGRADE_ROLES: frozenset[str] = frozenset({"maker", "governor", "checker"})

ROLE_ENV: dict[str, str] = {
    "maker": "EGLK_MODEL_MAKER",
    "checker": "EGLK_MODEL_CHECKER",
    "governor": "EGLK_MODEL_GOVERNOR",
    "explorer": "EGLK_MODEL_EXPLORER",
    "verifier": "EGLK_MODEL_VERIFIER",
    "pruner": "EGLK_MODEL_PRUNER",
    "refiner": "EGLK_MODEL_REFINER",
}


def resolve_model(role: str, *, env: Mapping[str, str] | None = None) -> str | None:
    """Return model id for role: per-role env → EGLK_MODEL → None."""
    env = env or os.environ
    key = ROLE_ENV.get(role.lower())
    if key and env.get(key, "").strip():
        return str(env[key]).strip()
    shared = env.get("EGLK_MODEL", "").strip()
    return shared or None


def may_downgrade(role: str) -> bool:
    return role.lower() not in NEVER_DOWNGRADE_ROLES
