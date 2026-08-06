"""CLI plugin subcommands."""

from __future__ import annotations

from eglk_harness.cli import build_parser


def test_plugin_list_subcommands():
    p = build_parser()
    ns = p.parse_args(["plugin", "list"])
    assert ns.func.__name__ == "_cmd_plugin"
    assert ns.plugin_command == "list"


def test_plugin_install_requires_name():
    p = build_parser()
    ns = p.parse_args(["plugin", "install", "--name", "codex-computer-use"])
    assert ns.plugin_command == "install"
    assert ns.name == "codex-computer-use"
