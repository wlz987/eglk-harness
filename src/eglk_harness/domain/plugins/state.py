"""User-scoped record of which computer-use plugins are installed.

State lives under ``~/.eglk-harness/plugins/`` (or ``EGLK_PLUGINS_ROOT`` /
``EGLK_HARNESS_STATE_ROOT/plugins``). ``eglk-harness run`` never installs.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import PluginError

CODEX_GUI_PLUGIN_ID = "codex-computer-use"
PLUGIN_PRIORITY: tuple[str, ...] = (CODEX_GUI_PLUGIN_ID, "open-computer-use", "clawdcursor")

_STATE_FILE = "installed.json"
_DEFAULT_STATE_ROOT = "~/.eglk-harness"


@dataclass(frozen=True)
class InstalledPlugin:
    plugin_id: str
    agents: tuple[str, ...]
    mcp_configs: dict[str, str]
    mcp_server_name: str = ""


def plugins_root() -> Path:
    env = os.environ.get("EGLK_PLUGINS_ROOT")
    if env:
        return Path(env).expanduser()
    root = os.environ.get("EGLK_HARNESS_STATE_ROOT") or _DEFAULT_STATE_ROOT
    return Path(root).expanduser() / "plugins"


def plugin_dir(plugin_id: str) -> Path:
    return plugins_root() / plugin_id


def state_path() -> Path:
    return plugins_root() / _STATE_FILE


def mcp_config_path(plugin_id: str, agent: str) -> Path:
    suffix = "toml" if agent == "codex" else "mcp.json"
    return plugin_dir(plugin_id) / agent / f"{plugin_id}.{suffix}"


def write_mcp_config(
    plugin_id: str,
    agent: str,
    *,
    server_name: str,
    command: str,
    args: list[str],
) -> Path:
    target = mcp_config_path(plugin_id, agent)
    if agent == "codex":
        from .codex_config import mcp_server_block

        _atomic_write(target, mcp_server_block(server_name, command, args))
        return target
    entry: dict[str, object] = {"command": command}
    if args:
        entry["args"] = list(args)
    payload = {"mcpServers": {server_name: entry}}
    _atomic_write(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return target


def record_install(
    plugin_id: str,
    *,
    agents: list[str],
    mcp_configs: dict[str, str] | None = None,
    mcp_server_name: str = "",
    version: str = "",
) -> None:
    state = _load()
    entry = state.get(plugin_id) if isinstance(state.get(plugin_id), dict) else {}
    known_agents = set(entry.get("agents") or []) if isinstance(entry, dict) else set()
    known_configs = dict(entry.get("mcp_configs") or {}) if isinstance(entry, dict) else {}
    known_agents.update(agents)
    if mcp_configs:
        known_configs.update(mcp_configs)
    state[plugin_id] = {
        "agents": sorted(known_agents),
        "mcp_configs": known_configs,
        "mcp_server_name": mcp_server_name or (entry.get("mcp_server_name") if isinstance(entry, dict) else "") or "",
        "version": version or (entry.get("version") if isinstance(entry, dict) else "") or "",
    }
    _save(state)


def forget_install(plugin_id: str) -> None:
    state = _load()
    if state.pop(plugin_id, None) is not None:
        _save(state)


def installed_plugins() -> dict[str, InstalledPlugin]:
    result: dict[str, InstalledPlugin] = {}
    for raw_id, entry in _load().items():
        if not isinstance(entry, dict):
            continue
        configs = entry.get("mcp_configs")
        result[str(raw_id)] = InstalledPlugin(
            plugin_id=str(raw_id),
            agents=tuple(str(a) for a in (entry.get("agents") or []) if str(a)),
            mcp_configs={
                str(k): str(v) for k, v in (configs if isinstance(configs, dict) else {}).items()
            },
            mcp_server_name=str(entry.get("mcp_server_name") or ""),
        )
    return result


def active_plugin_for_agent(agent: str) -> tuple[str, str] | None:
    state = _load()
    for plugin_id in PLUGIN_PRIORITY:
        if plugin_id == CODEX_GUI_PLUGIN_ID:
            if agent == "codex" and _codex_gui_ready():
                return plugin_id, ""
            continue
        entry = state.get(plugin_id)
        if not isinstance(entry, dict):
            continue
        if agent not in (entry.get("agents") or []):
            continue
        configs = entry.get("mcp_configs")
        raw = configs.get(agent) if isinstance(configs, dict) else None
        if raw is None:
            return plugin_id, ""
        path = Path(str(raw)).expanduser()
        if not path.is_file():
            continue
        return plugin_id, str(path)
    return None


def _codex_gui_ready() -> bool:
    from .codex_computer_use import COMPUTER_USE_PLUGIN_ID, get_codex_plugin_state

    try:
        return get_codex_plugin_state(COMPUTER_USE_PLUGIN_ID).ready
    except PluginError:
        return False


def _load() -> dict:
    target = state_path()
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginError(
            f"Could not read the plugin state at {target}: {exc}. "
            "Delete the file to reset it, then reinstall the plugins you need."
        ) from exc
    return data if isinstance(data, dict) else {}


def _save(state: dict) -> None:
    _atomic_write(state_path(), json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _atomic_write(target: Path, text: str) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent, delete=False
        ) as handle:
            handle.write(text)
            tmp = Path(handle.name)
        os.replace(tmp, target)
    except OSError as exc:
        raise PluginError(f"Could not write {target}: {exc}") from exc
