"""Backward-compatible re-export of Codex computer-use plugin helpers.

New code should import from ``eglk_harness.domain.plugins``.
"""

from eglk_harness.domain.plugins.codex_computer_use import (  # noqa: F401
    COMPUTER_USE_PLUGIN_ID,
    CodexPluginError,
    CodexPluginState,
    StatusCallback,
    _enable_plugin_in_user_config,
    _resolve_codex_binary,
    _run_codex,
    get_codex_plugin_state,
    install_computer_use_plugin,
    uninstall_computer_use_plugin,
)

__all__ = [
    "COMPUTER_USE_PLUGIN_ID",
    "CodexPluginError",
    "CodexPluginState",
    "StatusCallback",
    "get_codex_plugin_state",
    "install_computer_use_plugin",
    "uninstall_computer_use_plugin",
    "_run_codex",
    "_resolve_codex_binary",
    "_enable_plugin_in_user_config",
]
