"""CLI entry: ``eglk-harness``."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from eglk_harness import __version__
from eglk_harness.app import RunRequest, run as app_run
from eglk_harness.domain.check_projections import check_projections
from eglk_harness.domain.codex_plugins import (
    COMPUTER_USE_PLUGIN_ID,
    CodexPluginError,
    get_codex_plugin_state,
    install_computer_use_plugin,
    uninstall_computer_use_plugin,
)
from eglk_harness.domain.config_resolve import resolve_agent, resolve_compile, resolve_swarm
from eglk_harness.domain.doctor import run_doctor
from eglk_harness.domain.eval_runner import (
    default_eval_root,
    prepare_task_workdir,
    score_offline,
)
from eglk_harness.domain.init_project import init_project
from eglk_harness.domain.manifest import build_manifest, new_run_id, write_manifest
from eglk_harness.domain.models import resolve_model
from eglk_harness.domain.observe.dashboard import serve_dashboard
from eglk_harness.domain.status import collect_status
from eglk_harness.domain.update_check import check_update
from eglk_harness.domain import wa_hard as wa_hard_mod
from eglk_harness.domain import osworld as osworld_mod


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


def _doctor_line(level: str, name: str, detail: str) -> None:
    print(f"{level:4}  {name}: {detail}", flush=True)


def _cmd_doctor(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    code = 0
    if args.install_codex_gui or args.uninstall_codex_gui:
        try:
            if args.install_codex_gui:
                state = install_computer_use_plugin(
                    on_status=lambda s, m: _doctor_line("…. ", s, m),
                )
            else:
                state = uninstall_computer_use_plugin(
                    on_status=lambda s, m: _doctor_line("…. ", s, m),
                )
            if args.uninstall_codex_gui and not state.installed:
                _doctor_line("ok", "Codex GUI", f"{state.plugin_id} is not installed")
            elif state.ready:
                ver = f" v{state.version}" if state.version else ""
                _doctor_line("ok", "Codex GUI", f"{state.plugin_id}{ver} is installed and enabled")
            else:
                _doctor_line(
                    "FAIL",
                    "Codex GUI",
                    f"{state.plugin_id} installed={state.installed} enabled={state.enabled}",
                )
                code = 1
        except CodexPluginError as exc:
            _doctor_line("FAIL", "Codex GUI", str(exc))
            return 2
    else:
        try:
            state = get_codex_plugin_state(COMPUTER_USE_PLUGIN_ID)
            if state.ready:
                ver = f" v{state.version}" if state.version else ""
                _doctor_line("ok", "Codex GUI", f"{state.plugin_id}{ver} ready")
            elif state.available:
                _doctor_line(
                    "WARN",
                    "Codex GUI",
                    f"{state.plugin_id} available but not ready; "
                    "run `eglk-harness doctor --install-codex-gui`",
                )
            else:
                _doctor_line("WARN", "Codex GUI", f"{state.plugin_id} unavailable")
        except CodexPluginError as exc:
            _doctor_line("WARN", "Codex GUI", str(exc))

    report = run_doctor(workdir)
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
        if not c.ok:
            code = 1
    return code


def _cmd_run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    # Per-role model env overrides (CLI wins for this process)
    if args.maker_model:
        os.environ["EGLK_MODEL_MAKER"] = args.maker_model
    if args.checker_model:
        os.environ["EGLK_MODEL_CHECKER"] = args.checker_model
    if args.model:
        os.environ.setdefault("EGLK_MODEL", args.model)
        if not args.maker_model:
            os.environ["EGLK_MODEL_MAKER"] = args.model
        if not args.checker_model:
            os.environ["EGLK_MODEL_CHECKER"] = args.model

    kwargs: dict = {
        "workdir": workdir,
        "goal": args.goal,
        "agent": resolve_agent(args.agent, workdir),
        "swarm": resolve_swarm(args.swarm),
        "mcp_config": Path(args.mcp_config) if args.mcp_config else None,
        "mcp_add_dirs": list(args.mcp_add_dir or []),
        "compile": resolve_compile(args.compile, workdir),
        "maker_timeout_s": args.maker_timeout,
        "checker_timeout_s": args.checker_timeout,
    }
    if args.max_ticks is not None:
        kwargs["max_ticks"] = args.max_ticks
    if getattr(args, "tick", None) is not None:
        kwargs["tick"] = args.tick
    return app_run(RunRequest(**kwargs))


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


def _cmd_soak_bypass(args: argparse.Namespace) -> int:
    import asyncio

    from eglk_harness.domain.adapters.factory import create_adapter
    from eglk_harness.domain.bypass_soak import soak_bypass_roles

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    live = bool(args.live) or (os.environ.get("EGLK_SOAK_LIVE") or "").strip() in {
        "1",
        "on",
        "true",
        "yes",
    }
    agent = str(args.agent)
    if live and agent == "mock":
        print("error: --live requires --agent codex|claude_code", flush=True)
        return 2
    if not live and agent != "mock":
        # still allow explicit live backends without --live flag
        live = True
    adapter = create_adapter(agent, model=args.model)
    # Always force episodes during soak so mock path exercises bypass JSON.
    force = True
    report = asyncio.run(
        soak_bypass_roles(
            adapter,
            workdir,
            timeout_s=float(args.timeout),
            force=force,
        )
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    llm_hits = sum(1 for r in report.roles if r.source == "llm")
    print(
        f"soak-bypass agent={report.agent} ok={report.ok} llm_roles={llm_hits}/{len(report.roles)} "
        f"report={workdir}/.eglk-harness/soak/bypass/report.json",
        flush=True,
    )
    if live and llm_hits == 0:
        print("warning: live soak produced zero llm sources (check backend / model)", flush=True)
        return 1
    return 0 if report.ok else 1


def _cmd_check_update(_args: argparse.Namespace) -> int:
    result = check_update()
    print(f"{result.package}: {result.detail}")
    return 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    serve_dashboard(
        Path(args.workdir).resolve(),
        host=args.host,
        port=int(args.port),
        blocking=True,
    )
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    eval_root = Path(args.eval_root).resolve() if args.eval_root else default_eval_root()
    if eval_root is None or not eval_root.is_dir():
        print(
            "error: eval root not found; pass --eval-root "
            "(expected alw/experiment/eval). Scorers never feed Gate.",
            flush=True,
        )
        return 2
    out = Path(args.workdir).resolve()
    if args.suite == "wa_hard":
        tasks = {t.task_id: t for t in wa_hard_mod.load_pack_index(eval_root)}
        task = tasks.get(args.task_id)
        if task is None:
            print(f"error: unknown wa_hard task_id={args.task_id}", flush=True)
            return 2
        wa_hard_mod.materialize_goal(task, out)
    elif args.suite == "osworld_aux":
        tasks = {t.task_id: t for t in osworld_mod.load_pack_index(eval_root)}
        task = tasks.get(args.task_id)
        if task is None:
            print(f"error: unknown osworld_aux task_id={args.task_id}", flush=True)
            return 2
        osworld_mod.materialize_goal(task, out)
    else:
        prepare_task_workdir(eval_root, suite=args.suite, task_id=args.task_id, out_dir=out)
    init_project(out)
    print(f"prepared eval workdir {out} suite={args.suite} task={args.task_id}")
    if args.prepare_only:
        return 0
    rc = app_run(
        RunRequest(
            workdir=out,
            agent=resolve_agent(args.agent, out),
            swarm=resolve_swarm(args.swarm or "0"),
            compile=resolve_compile(args.compile, out),
            max_ticks=int(args.max_ticks or 4),
        )
    )
    if args.suite == "wa_hard":
        scores = wa_hard_mod.score_placeholder(task_id=args.task_id, workdir=out)
        ok = True
        detail = "recorded_only"
    elif args.suite == "osworld_aux":
        scores = osworld_mod.score_placeholder(task_id=args.task_id, workdir=out)
        ok = True
        detail = "recorded_only"
    else:
        scored = score_offline(
            suite=args.suite, task_id=args.task_id, workdir=out, eval_root=eval_root
        )
        scores, ok, detail = scored.scores, scored.ok, scored.detail
    run_id = new_run_id("eval")
    manifest = build_manifest(
        run_id=run_id,
        workdir=out,
        goal_id=f"eval-{args.suite}-{args.task_id}",
        agent=str(args.agent),
        model=resolve_model("maker"),
        swarm=args.swarm,
        extra={"scores": scores, "eval_ok": ok, "eval_detail": detail},
    )
    path = write_manifest(out, manifest)
    print(json.dumps({"eval": scores, "ok": ok, "detail": detail, "manifest": str(path)}, indent=2))
    print("note: offline scores are Manifest-only — never Gate inputs")
    return rc if rc else (0 if ok else 1)


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

    doc_p = sub.add_parser("doctor", help="Check environment; optional Codex GUI install")
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
    run_p.add_argument("--model", default=None, help="Shared model id (EGLK_MODEL)")
    run_p.add_argument("--maker-model", default=None, help="Maker model override")
    run_p.add_argument("--checker-model", default=None, help="Checker model override")
    run_p.add_argument("--maker-timeout", type=float, default=None, help="Maker episode timeout (s)")
    run_p.add_argument(
        "--checker-timeout", type=float, default=None, help="Checker episode timeout (s)"
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
    run_p.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Soft tick safety cap (default 32); does NOT replace cognitive/repairs abort",
    )
    run_p.add_argument(
        "--tick",
        type=int,
        default=None,
        help="Start tick index (default: auto-resume from state.json + 1)",
    )
    run_p.set_defaults(func=_cmd_run)

    st_p = sub.add_parser("status", help="Read-only status of harness dirs / runs")
    st_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    st_p.add_argument("--run", default=None, help="Select loop/<run_id> (default: newest)")
    st_p.set_defaults(func=_cmd_status)

    dash = sub.add_parser("dashboard", help="Read-only HTTP dashboard (never an approval gate)")
    dash.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8766)
    dash.set_defaults(func=_cmd_dashboard)

    cu = sub.add_parser("check-update", help="Check PyPI for a newer eglk-harness (no auto-upgrade)")
    cu.set_defaults(func=_cmd_check_update)

    ev = sub.add_parser(
        "eval",
        help="Auxiliary eval suite runner (offline scores never feed Gate)",
    )
    ev.add_argument("--suite", required=True, choices=("weave_thin", "wa_hard", "osworld_aux", "scenarios"))
    ev.add_argument("--task-id", required=True)
    ev.add_argument("--eval-root", default=None, help="Path to experiment/eval (default: auto)")
    ev.add_argument("--workdir", default="./.eglk-eval-workdir", help="Materialized task workdir")
    ev.add_argument("--agent", default="mock", choices=("mock", "codex", "claude_code"))
    ev.add_argument("--swarm", default="0")
    ev.add_argument("--compile", default="off", choices=("auto", "force", "off"))
    ev.add_argument("--max-ticks", type=int, default=4)
    ev.add_argument("--prepare-only", action="store_true", help="Only write .goal.md / init")
    ev.set_defaults(func=_cmd_eval)

    cp = sub.add_parser(
        "check-projections",
        help="CI pin: assert thresholds match design/kernel/projections.md",
    )
    cp.set_defaults(func=_cmd_check_projections)

    soak = sub.add_parser(
        "soak-bypass",
        help="Soak Governor/Explorer/Verifier/Refiner/compile (no tools; Gate not involved)",
    )
    soak.add_argument("--workdir", default="./.eglk-soak-bypass", help="Scratch workdir for soak artifacts")
    soak.add_argument("--agent", default="mock", choices=("mock", "codex", "claude_code"))
    soak.add_argument("--model", default=None, help="Override model for live backends")
    soak.add_argument("--timeout", type=float, default=120.0, help="Per-role episode timeout seconds")
    soak.add_argument(
        "--live",
        action="store_true",
        help="Require live backend LLM hits (also EGLK_SOAK_LIVE=1); fails if zero llm sources",
    )
    soak.set_defaults(func=_cmd_soak_bypass)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
