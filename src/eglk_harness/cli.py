"""CLI entry: ``eglk-harness``."""

from __future__ import annotations

import argparse
from pathlib import Path

from eglk_harness import __version__
from eglk_harness.app import RunRequest, run as app_run
from eglk_harness.domain.check_projections import check_projections
from eglk_harness.domain.config_resolve import resolve_agent, resolve_compile, resolve_swarm
from eglk_harness.domain.doctor import run_doctor
from eglk_harness.domain.init_project import init_project
from eglk_harness.domain.status import collect_status


def _cmd_init(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    result = init_project(workdir, force=args.force)
    for p in result.created:
        print(f"created  {p}")
    for p in result.skipped:
        print(f"skipped  {p}")
    if not result.created and result.skipped:
        print("(nothing written; pass --force to overwrite files)")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    if args.install_codex_gui or args.uninstall_codex_gui:
        print(
            "error: Codex GUI install/uninstall is reserved for a later milestone; "
            "doctor remains check-only.",
            flush=True,
        )
        return 2
    report = run_doctor(Path(args.workdir).resolve())
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
    return 0 if report.ok else 1


def _cmd_run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    return app_run(
        RunRequest(
            workdir=workdir,
            goal=args.goal,
            agent=resolve_agent(args.agent, workdir),
            swarm=resolve_swarm(args.swarm),
            mcp_config=Path(args.mcp_config) if args.mcp_config else None,
            mcp_add_dirs=list(args.mcp_add_dir or []),
            compile=resolve_compile(args.compile, workdir),
        )
    )


def _cmd_status(args: argparse.Namespace) -> int:
    report = collect_status(Path(args.workdir).resolve(), run_id=args.run)
    print(report.render())
    return 0


def _cmd_check_projections(_args: argparse.Namespace) -> int:
    report = check_projections()
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eglk-harness",
        description="Evidence-Gated Loop Kernel harness",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create .eglk-harness skeleton and .goal.md")
    init_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    init_p.add_argument("--force", action="store_true", help="Overwrite existing files")
    init_p.set_defaults(func=_cmd_init)

    doc_p = sub.add_parser("doctor", help="Check environment (read-only)")
    doc_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    doc_p.add_argument(
        "--install-codex-gui",
        action="store_true",
        help="Explicitly install Codex Computer Use (not automatic on run)",
    )
    doc_p.add_argument(
        "--uninstall-codex-gui",
        action="store_true",
        help="Explicitly uninstall Codex Computer Use",
    )
    doc_p.set_defaults(func=_cmd_doctor)

    run_p = sub.add_parser("run", help="Start a harness run")
    run_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    run_p.add_argument("--goal", "--task", dest="goal", default=None, help="Goal text or path")
    run_p.add_argument(
        "--agent",
        default=None,
        choices=("mock", "codex", "claude_code"),
        help="Backend agent (default: EGLK_AGENT / config.toml / mock)",
    )
    run_p.add_argument("--swarm", default=None, help="0|1 soft switch for Phase-0 SWARM")
    run_p.add_argument(
        "--compile",
        default=None,
        choices=("auto", "force", "off"),
        help="STEP 0 goal compile mode (default: auto / EGLK_COMPILE)",
    )
    run_p.add_argument("--mcp-config", default=None, help="Claude-shaped mcp.json (opt-in)")
    run_p.add_argument(
        "--mcp-add-dir",
        action="append",
        default=None,
        help="Extra readable dir for Maker/Checker MCP (repeatable)",
    )
    run_p.set_defaults(func=_cmd_run)

    st_p = sub.add_parser("status", help="Read-only status of harness dirs / runs")
    st_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    st_p.add_argument("--run", default=None, help="Select loop/<run_id> (default: newest)")
    st_p.set_defaults(func=_cmd_status)

    cp = sub.add_parser(
        "check-projections",
        help="CI pin: assert thresholds match design/kernel/projections.md",
    )
    cp.set_defaults(func=_cmd_check_projections)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
