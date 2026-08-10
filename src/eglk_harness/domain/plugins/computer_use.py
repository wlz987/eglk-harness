"""Universal computer-use surface — one contract for Codex GUI + community MCP plugins.

Computer-use is opt-in (``eglk-harness plugin install`` / ``doctor --install-codex-gui``);
``run`` never installs. When enabled, Maker/Checker MCP allowlists are enriched so GUI
servers stay reachable without hand-editing ``EGLK_MCP_ALLOW_*``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from eglk_harness.domain.plugins.community_computer_use import (
    COMMUNITY_PLUGINS,
    community_plugin_activation,
)
from eglk_harness.domain.plugins.errors import PluginError
from eglk_harness.domain.plugins.state import (
    CODEX_GUI_PLUGIN_ID,
    PLUGIN_PRIORITY,
    active_plugin_for_agent,
    installed_plugins,
)

# Canonical MCP server names used across vendors (for allowlist enrichment).
KNOWN_COMPUTER_USE_MCP_NAMES: frozenset[str] = frozenset(
    {
        "computer-use",
        "open-computer-use",
        "clawdcursor",
    }
)


@dataclass(frozen=True)
class ComputerUsePluginStatus:
    plugin_id: str
    kind: str  # codex_bundled | community_mcp
    ready: bool
    detail: str
    mcp_server_name: str = ""
    mcp_config_path: str = ""


def computer_use_mode(env: Mapping[str, str] | None = None) -> str:
    """``EGLK_COMPUTER_USE``: auto | on | off (default auto)."""
    env = env or os.environ
    raw = (env.get("EGLK_COMPUTER_USE") or "auto").strip().lower()
    if raw in {"0", "off", "false", "no", "none"}:
        return "off"
    if raw in {"1", "on", "true", "yes", "force"}:
        return "on"
    return "auto"


def computer_use_enabled(env: Mapping[str, str] | None = None) -> bool:
    mode = computer_use_mode(env)
    if mode == "off":
        return False
    if mode == "on":
        return True
    # auto: any installed/active computer-use plugin
    for agent in ("codex", "claude_code"):
        if active_plugin_for_agent(agent) is not None:
            return True
    return False


def computer_use_server_names_for_agent(
    agent: str,
    *,
    env: Mapping[str, str] | None = None,
) -> frozenset[str]:
    """MCP server names to keep reachable for GUI control on this agent backend."""
    if not computer_use_enabled(env):
        return frozenset()
    active = active_plugin_for_agent(agent)
    if active is None:
        return frozenset()
    plugin_id, mcp_path = active
    if plugin_id == CODEX_GUI_PLUGIN_ID:
        # Official Codex plugin: tools via Codex CLI, not harness MCP file.
        return frozenset()
    entry = installed_plugins().get(plugin_id)
    name = (entry.mcp_server_name if entry else "") or plugin_id
    if name:
        return frozenset({name})
    if mcp_path:
        return frozenset({plugin_id})
    return frozenset()


def enrich_mcp_allowlist(
    role: str,
    allow: frozenset[str] | None,
    *,
    env: Mapping[str, str] | None = None,
) -> frozenset[str] | None:
    """When computer-use is active, ensure its MCP server names survive role allowlists."""
    if allow is None:
        return None
    env = env or os.environ
    if not computer_use_enabled(env):
        return allow
    if role.lower() not in {"maker", "checker"}:
        return allow
    agent = (env.get("EGLK_AGENT") or "codex").strip().lower()
    if agent in {"mock", "fake"}:
        return allow
    names = computer_use_server_names_for_agent(agent, env=env)
    if not names:
        return allow
    return allow | names


def collect_computer_use_status() -> list[ComputerUsePluginStatus]:
    """Read-only status for doctor / status (never installs)."""
    rows: list[ComputerUsePluginStatus] = []
    try:
        from eglk_harness.domain.plugins.codex_computer_use import (
            COMPUTER_USE_PLUGIN_ID,
            get_codex_plugin_state,
        )

        state = get_codex_plugin_state(COMPUTER_USE_PLUGIN_ID)
        if state.available:
            detail = (
                f"ready v{state.version}".strip()
                if state.ready
                else (
                    "installed but disabled"
                    if state.installed
                    else "available; run eglk-harness plugin install --name codex-computer-use"
                )
            )
            rows.append(
                ComputerUsePluginStatus(
                    plugin_id=CODEX_GUI_PLUGIN_ID,
                    kind="codex_bundled",
                    ready=state.ready,
                    detail=detail,
                )
            )
        else:
            rows.append(
                ComputerUsePluginStatus(
                    plugin_id=CODEX_GUI_PLUGIN_ID,
                    kind="codex_bundled",
                    ready=False,
                    detail="unavailable on this Codex build",
                )
            )
    except PluginError as exc:
        rows.append(
            ComputerUsePluginStatus(
                plugin_id=CODEX_GUI_PLUGIN_ID,
                kind="codex_bundled",
                ready=False,
                detail=str(exc),
            )
        )

    installed = installed_plugins()
    for plugin in COMMUNITY_PLUGINS:
        entry = installed.get(plugin.plugin_id)
        mcp_path = ""
        if entry and entry.mcp_configs:
            agent = plugin.agents[0]
            mcp_path = entry.mcp_configs.get(agent, "")
        ready = entry is not None
        detail = "not installed"
        if entry:
            detail = f"installed for {','.join(entry.agents)}"
            try:
                act, detail_path = community_plugin_activation(plugin)
                if act is True:
                    detail += "; activation ok"
                elif act is False:
                    detail += "; activation pending"
            except PluginError as exc:
                detail += f"; {exc}"
        rows.append(
            ComputerUsePluginStatus(
                plugin_id=plugin.plugin_id,
                kind="community_mcp",
                ready=ready,
                detail=detail,
                mcp_server_name=plugin.mcp_server_name,
                mcp_config_path=mcp_path,
            )
        )
    return rows


def active_computer_use_summary(agent: str) -> str:
    active = active_plugin_for_agent(agent)
    if active is None:
        return "none"
    pid, path = active
    if path:
        return f"{pid} mcp={path}"
    return f"{pid} (bundled)"


def doctor_computer_use_detail() -> tuple[bool, str]:
    """Aggregate line for doctor: ok when mode off or at least one path is ready."""
    mode = computer_use_mode()
    if mode == "off":
        return True, "EGLK_COMPUTER_USE=off"
    statuses = collect_computer_use_status()
    ready = [s for s in statuses if s.ready]
    codex_ready = any(s.plugin_id == CODEX_GUI_PLUGIN_ID and s.ready for s in statuses)
    community_ready = any(s.kind == "community_mcp" and s.ready for s in statuses)
    parts = [f"mode={mode}", f"priority={' > '.join(PLUGIN_PRIORITY)}"]
    for agent in ("codex", "claude_code"):
        parts.append(f"{agent}={active_computer_use_summary(agent)}")
    if mode == "on" and not (codex_ready or community_ready):
        return False, "; ".join(parts) + "; EGLK_COMPUTER_USE=on but no plugin ready"
    if mode == "auto" and not ready:
        parts.append("hint=eglk-harness plugin install --name open-computer-use")
    return True, "; ".join(parts)
