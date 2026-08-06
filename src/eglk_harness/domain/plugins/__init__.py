"""Optional agent-CLI plugin setup, kept out of the task-execution path.

Plugins are installed or removed only through explicit ``eglk-harness doctor``
or ``eglk-harness plugin`` opt-in; ``eglk-harness run`` never changes them.

Codex helpers live in ``.codex_computer_use`` and are re-exported lazily here
to avoid import cycles with that module.
"""

from __future__ import annotations

from typing import Any

from .community_computer_use import (
    AGENT_CLAUDE_CODE,
    AGENT_CODEX,
    COMMUNITY_PLUGINS,
    CommunityPlugin,
    community_plugin_activation,
    community_plugin_ids,
    community_plugin_state,
    get_community_plugin,
    global_registrations,
    install_community_plugin,
    uninstall_community_plugin,
)
from .errors import PluginError
from .npm import NpmPackageState, node_version, npm_binary, npm_version
from .state import (
    CODEX_GUI_PLUGIN_ID,
    PLUGIN_PRIORITY,
    InstalledPlugin,
    active_plugin_for_agent,
    installed_plugins,
    plugins_root,
)

_CODEX_EXPORTS = frozenset(
    {
        "COMPUTER_USE_PLUGIN_ID",
        "CodexPluginError",
        "CodexPluginState",
        "codex_gui_grants",
        "get_codex_plugin_state",
        "install_computer_use_plugin",
        "runtime_app_path",
        "uninstall_computer_use_plugin",
    }
)


def __getattr__(name: str) -> Any:
    if name in _CODEX_EXPORTS:
        from . import codex_computer_use as _codex

        return getattr(_codex, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AGENT_CLAUDE_CODE",
    "AGENT_CODEX",
    "CODEX_GUI_PLUGIN_ID",
    "COMMUNITY_PLUGINS",
    "COMPUTER_USE_PLUGIN_ID",
    "PLUGIN_PRIORITY",
    "CodexPluginError",
    "CodexPluginState",
    "CommunityPlugin",
    "InstalledPlugin",
    "NpmPackageState",
    "PluginError",
    "active_plugin_for_agent",
    "codex_gui_grants",
    "community_plugin_activation",
    "community_plugin_ids",
    "community_plugin_state",
    "get_codex_plugin_state",
    "get_community_plugin",
    "global_registrations",
    "install_community_plugin",
    "install_computer_use_plugin",
    "installed_plugins",
    "node_version",
    "npm_binary",
    "npm_version",
    "plugins_root",
    "runtime_app_path",
    "uninstall_community_plugin",
    "uninstall_computer_use_plugin",
]
