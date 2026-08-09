"""Shared / per-role model resolution (economics lite — shared model first)."""

from __future__ import annotations

import os
from typing import Any, Mapping

# Maker / Governor / Checker never downgrade (model economics contract).
NEVER_DOWNGRADE_ROLES: frozenset[str] = frozenset({"maker", "governor", "checker"})

ROLE_ENV: dict[str, str] = {
    "maker": "EGLK_MODEL_MAKER",
    "checker": "EGLK_MODEL_CHECKER",
    "governor": "EGLK_MODEL_GOVERNOR",
    "explorer": "EGLK_MODEL_EXPLORER",
    "verifier": "EGLK_MODEL_VERIFIER",
    "pruner": "EGLK_MODEL_PRUNER",
    "refiner": "EGLK_MODEL_REFINER",
    "compile": "EGLK_MODEL_COMPILE",
}

DOWNGRADE_ENV: dict[str, str] = {
    "verifier": "EGLK_MODEL_DOWNGRADE_VERIFIER",
    "refiner": "EGLK_MODEL_DOWNGRADE_REFINER",
}

# Process-local plan written by Phase-3 context-compress; Gate never reads this.
_ACTIVE_DOWNGRADE: dict[str, str] = {}

def set_active_downgrade(roles: Mapping[str, str] | None) -> None:
    """Install (or clear) Verifier/Refiner downgrade overrides for this process."""
    global _ACTIVE_DOWNGRADE
    clean: dict[str, str] = {}
    for role, model in dict(roles or {}).items():
        r = str(role).lower()
        if not may_downgrade(r):
            continue
        m = str(model).strip()
        if m:
            clean[r] = m
    _ACTIVE_DOWNGRADE = clean

def get_active_downgrade() -> dict[str, str]:
    return dict(_ACTIVE_DOWNGRADE)

def resolve_model(role: str, *, env: Mapping[str, str] | None = None) -> str | None:
    """Return model id for role: downgrade (if allowed) → per-role env → EGLK_MODEL → None."""
    env = env or os.environ
    r = role.lower()
    if may_downgrade(r) and r in _ACTIVE_DOWNGRADE:
        return _ACTIVE_DOWNGRADE[r]
    key = ROLE_ENV.get(r)
    if key and env.get(key, "").strip():
        return str(env[key]).strip()
    shared = env.get("EGLK_MODEL", "").strip()
    return shared or None

def may_downgrade(role: str) -> bool:
    return role.lower() not in NEVER_DOWNGRADE_ROLES

def plan_model_downgrade(
    *,
    usd_used: float,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Decide Verifier/Refiner downgrades from USD spend (Maker/Governor/Checker never)."""
    env = env or os.environ
    raw = (env.get("EGLK_MODEL_DOWNGRADE_THRESHOLD_USD") or "").strip()
    try:
        threshold = float(raw) if raw else None
    except ValueError:
        threshold = None
    if threshold is None or usd_used <= threshold:
        return {
            "active": False,
            "usd_used": usd_used,
            "threshold": threshold,
            "roles": {},
        }
    roles: dict[str, str] = {}
    for role, key in DOWNGRADE_ENV.items():
        val = (env.get(key) or "").strip()
        if val and may_downgrade(role):
            roles[role] = val
    return {
        "active": bool(roles),
        "usd_used": usd_used,
        "threshold": threshold,
        "roles": roles,
    }
