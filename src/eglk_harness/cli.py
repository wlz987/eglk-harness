"""CLI entry: ``eglk-harness``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eglk_harness import __version__
from eglk_harness.app import RunRequest, run as app_run
from eglk_harness.domain.doctor import run_doctor
from eglk_harness.domain.init_project import init_project
from eglk_harness.domain import paths


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
            "doctor remains check-only in M0.",
            flush=True,
        )
        return 2
    report = run_doctor(Path(args.workdir).resolve())
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
    return 0 if report.ok else 1


def _cmd_run(args: argparse.Namespace) -> int:
    return app_run(
        RunRequest(
            workdir=Path(args.workdir).resolve(),
            goal=args.goal,
            agent=args.agent,
            swarm=args.swarm,
            mcp_config=Path(args.mcp_config) if args.mcp_config else None,
        )
    )


def _cmd_status(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    harness = paths.harness_root(workdir)
    loop = paths.loop_root(workdir)
    memory = paths.memory_root(workdir)
    print(f"workdir:  {workdir}")
    print(f"harness:  {harness}  ({'yes' if harness.is_dir() else 'no'})")
    print(f"loop:     {loop}  ({'yes' if loop.is_dir() else 'no'})")
    print(f"memory:   {memory}  ({'yes' if memory.is_dir() else 'no'})")
    print(f"goal:     {paths.goal_path(workdir)}  ({'yes' if paths.goal_path(workdir).is_file() else 'no'})")
    if loop.is_dir():
        runs = sorted(p.name for p in loop.iterdir() if p.is_dir())
        print(f"runs:     {', '.join(runs) if runs else '(none)'}")
    print("(status is read-only; no approval controls)")
    return 0


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
        help="Explicitly install Codex Computer Use (not in M0)",
    )
    doc_p.add_argument(
        "--uninstall-codex-gui",
        action="store_true",
        help="Explicitly uninstall Codex Computer Use (not in M0)",
    )
    doc_p.set_defaults(func=_cmd_doctor)

    run_p = sub.add_parser("run", help="Start a harness run")
    run_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    run_p.add_argument("--goal", "--task", dest="goal", default=None, help="Goal text or path")
    run_p.add_argument(
        "--agent",
        default="codex",
        choices=("codex", "claude_code"),
        help="Backend agent (default: codex)",
    )
    run_p.add_argument("--swarm", default=None, help="0|1 soft switch")
    run_p.add_argument("--mcp-config", default=None, help="Claude-shaped mcp.json (opt-in)")
    run_p.set_defaults(func=_cmd_run)

    st_p = sub.add_parser("status", help="Read-only status of harness dirs / runs")
    st_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    st_p.set_defaults(func=_cmd_status)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
