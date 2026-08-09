"""Backward-compatible re-export of Codex computer-use plugin helpers.

New code should import from ``eglk_harness.domain.plugins``.
"""

from eglk_harness.domain.plugins.codex_computer_use import (  # noqa: F401
    COMPUTER_USE_PLUGIN_ID,
    CodexPluginError,
    CodexPluginState,
    StatusCallback,
    codex_gui_grants,
    get_codex_plugin_state,
    install_computer_use_plugin,
    runtime_app_path,
    uninstall_computer_use_plugin,
    _enable_plugin_in_user_config,
    _resolve_codex_binary,
    _run_codex,
)

__all__ = [
    "COMPUTER_USE_PLUGIN_ID",
    "CodexPluginError",
    "CodexPluginState",
    "StatusCallback",
    "codex_gui_grants",
    "get_codex_plugin_state",
    "install_computer_use_plugin",
    "runtime_app_path",
    "uninstall_computer_use_plugin",
    "_run_codex",
    "_resolve_codex_binary",
    "_enable_plugin_in_user_config",
]
