"""Per-role tool / MCP profiles (design: multi_agent §8 · adapters §3).

Policy 2+3: every session role may hold tools by default (Maker-level surface);
operators tighten via ``EGLK_MCP_ALLOW_<ROLE>`` allowlists. Gate has no session.
Format-repair episodes stay tools-off. SWARM still must not write claims/evidence/decisions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

# Roles that open an Adapter episode (Gate is mechanical — no tools).
SESSION_ROLES: frozenset[str] = frozenset(
    {
        "maker",
        "checker",
        "governor",
        "explorer",
        "verifier",
        "pruner",
        "refiner",
        "compile",
    }
)

# Backward-compat alias: historically only Maker/Checker; now all session roles.
TOOL_ROLES: frozenset[str] = SESSION_ROLES


@dataclass(frozen=True)
class RoleToolProfile:
    """Resolved tool surface for one role episode."""

    tools_allowed: bool
    # None → all MCP servers in config; frozenset → intersect; empty → no MCP servers.
    mcp_server_allowlist: frozenset[str] | None


def _env_map(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return env if env is not None else os.environ


def _parse_allowlist(raw: str) -> frozenset[str] | None:
    """Parse allowlist string. ``*`` / empty-after-strip meaning:

    - ``*`` or ``all`` → None (unrestricted)
    - ``-`` or ``none`` or ``off`` → empty frozenset (tools ok, no MCP servers)
    - ``a,b,c`` → frozenset of names
    """
    s = raw.strip()
    if not s or s in {"*", "all", "ANY", "any"}:
        return None
    if s.lower() in {"-", "none", "off", "empty"}:
        return frozenset()
    return frozenset(p.strip() for p in s.split(",") if p.strip())


def tools_forced_off(role: str, *, env: Mapping[str, str] | None = None) -> bool:
    env = _env_map(env)
    raw = (env.get("EGLK_TOOLS_OFF_ROLES") or "").strip()
    if not raw:
        return False
    off = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return role.lower() in off


def resolve_role_tool_profile(
    role: str,
    *,
    env: Mapping[str, str] | None = None,
) -> RoleToolProfile:
    """Default: tools on for all session roles; MCP unrestricted unless allowlist set."""
    r = role.lower().strip()
    if r not in SESSION_ROLES:
        return RoleToolProfile(tools_allowed=False, mcp_server_allowlist=frozenset())
    if tools_forced_off(r, env=env):
        return RoleToolProfile(tools_allowed=False, mcp_server_allowlist=frozenset())

    env = _env_map(env)
    key = f"EGLK_MCP_ALLOW_{r.upper()}"
    if key in env and str(env.get(key, "")).strip() != "":
        allow = _parse_allowlist(str(env.get(key) or ""))
    else:
        # Global default allowlist applies when per-role unset.
        g = (env.get("EGLK_MCP_ALLOW_DEFAULT") or "").strip()
        allow = _parse_allowlist(g) if g else None
    return RoleToolProfile(tools_allowed=True, mcp_server_allowlist=allow)


def assert_tools_for_role(
    role: str,
    *,
    tools_allowed: bool,
    env: Mapping[str, str] | None = None,
) -> None:
    """Hard fail only when tools requested for a non-session role or forced-off role."""
    if not tools_allowed:
        return
    profile = resolve_role_tool_profile(role, env=env)
    if not profile.tools_allowed:
        raise AssertionError(
            f"refusing to attach tools/MCP to role={role!r}; "
            f"profile.tools_allowed=False (session={role.lower() in SESSION_ROLES})"
        )
