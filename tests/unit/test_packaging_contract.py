"""Packaging / design shell contract — CLI surface and config priority."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.cli import build_parser
from eglk_harness.domain.eval import EVAL_SUITES
from eglk_harness.domain.product.config_resolve import resolve_agent, resolve_compile, resolve_swarm
from eglk_harness.domain.product.runtime_bootstrap import (
    apply_config_toml,
    apply_dotenv,
    bootstrap_workdir,
    want_dashboard,
)

# packaging.md §3.1 — keep in sync
_REQUIRED_COMMANDS = frozenset(
    {
        "init",
        "doctor",
        "plugin",
        "run",
        "status",
        "dashboard",
        "check-update",
        "eval",
        "soak-bypass",
        "check-projections",
    }
)


def test_cli_commands_match_packaging():
    parser = build_parser()
    # argparse subparsers store choices on the action
    subs = None
    for action in parser._actions:
        if getattr(action, "dest", None) == "command":
            subs = set(action.choices or {})
            break
    assert subs is not None
    missing = _REQUIRED_COMMANDS - subs
    assert not missing, f"CLI missing packaging commands: {sorted(missing)}"


def test_run_has_dashboard_flag():
    ns = build_parser().parse_args(["run", "--dashboard", "--workdir", "."])
    assert ns.dashboard is True


def test_config_beats_env_for_agent(tmp_path: Path, monkeypatch):
    harness = tmp_path / ".eglk-harness"
    harness.mkdir()
    (harness / "config.toml").write_text(
        '[run]\ndefault_agent = "codex"\ncompile = "force"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EGLK_AGENT", "mock")
    monkeypatch.setenv("EGLK_COMPILE", "off")
    apply_config_toml(tmp_path)
    assert resolve_agent(None, tmp_path) == "codex"
    assert resolve_compile(None, tmp_path) == "force"


def test_cli_beats_config(tmp_path: Path, monkeypatch):
    harness = tmp_path / ".eglk-harness"
    harness.mkdir()
    (harness / "config.toml").write_text('[run]\ndefault_agent = "codex"\n', encoding="utf-8")
    monkeypatch.delenv("EGLK_AGENT", raising=False)
    apply_config_toml(tmp_path)
    assert resolve_agent("claude_code", tmp_path) == "claude_code"


def test_dotenv_then_config_bootstrap(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text("EGLK_PROMPT_LANGUAGE=en\nEGLK_AGENT=mock\n", encoding="utf-8")
    harness = tmp_path / ".eglk-harness"
    harness.mkdir()
    (harness / "config.toml").write_text(
        '[run]\ndefault_agent = "codex"\n[observe]\nprompt_language = "zh"\n',
        encoding="utf-8",
    )
    for key in ("EGLK_AGENT", "EGLK_PROMPT_LANGUAGE", "EGLK_DASHBOARD"):
        monkeypatch.delenv(key, raising=False)
    bootstrap_workdir(tmp_path)
    assert resolve_agent(None, tmp_path) == "codex"
    assert want_dashboard(cli_flag=None) is False  # dashboard default false
    # prompt_language from observe
    from eglk_harness.domain.runtime.prompt_i18n import prompt_language

    assert prompt_language() == "zh"


def test_swarm_from_config(tmp_path: Path, monkeypatch):
    harness = tmp_path / ".eglk-harness"
    harness.mkdir()
    (harness / "config.toml").write_text('[run]\nswarm = "0"\n', encoding="utf-8")
    monkeypatch.delenv("EGLK_SWARM", raising=False)
    apply_config_toml(tmp_path)
    assert resolve_swarm(None, tmp_path) == "0"


def test_eval_suite_choices_match_constant():
    parser = build_parser()
    ns = parser.parse_args(["eval", "--suite", "weave_lh", "--list-tasks"])
    assert ns.suite in EVAL_SUITES
    found = None

    def walk(pr):
        nonlocal found
        for action in pr._actions:
            if getattr(action, "dest", None) == "suite":
                found = set(action.choices or {})
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for sub in choices.values():
                    walk(sub)

    walk(parser)
    assert found == set(EVAL_SUITES), found


def test_status_json_flag_present():
    ns = build_parser().parse_args(["status", "--json", "--workdir", "."])
    assert ns.json is True
