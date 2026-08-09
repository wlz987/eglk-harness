"""CLI entry: ``eglk-harness``."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from eglk_harness import __version__
from eglk_harness.app import RunRequest, run as app_run
from eglk_harness.domain.product.check_projections import check_projections
from eglk_harness.domain.plugins.codex_computer_use import (
    COMPUTER_USE_PLUGIN_ID,
    CodexPluginError,
    get_codex_plugin_state,
    install_computer_use_plugin,
    uninstall_computer_use_plugin,
)
from eglk_harness.domain.product.config_resolve import resolve_agent, resolve_compile, resolve_swarm
from eglk_harness.domain.product.doctor import run_doctor
from eglk_harness.domain.eval.paths import default_eval_root
from eglk_harness.domain.eval.eval_runner import (
    prepare_task_workdir,
    score_offline,
)
from eglk_harness.domain.product.init_project import init_project
from eglk_harness.domain.product.manifest import build_manifest, new_run_id, write_manifest
from eglk_harness.domain.runtime.models import resolve_model
from eglk_harness.domain.product.observe.dashboard import serve_dashboard
from eglk_harness.domain.product.status import collect_status
from eglk_harness.domain.product.update_check import check_update
from eglk_harness.domain.eval.loader import eval_suite_choices, load_suite_module

def _suite_mod(suite: str, eval_root: Path):
    return load_suite_module(suite, eval_root)

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

_CODEX_GUI_PLUGIN = "codex-computer-use"
_PLUGIN_CHOICES = (_CODEX_GUI_PLUGIN, "open-computer-use", "clawdcursor")

def _cmd_plugin(args: argparse.Namespace) -> int:
    """Install/list/uninstall computer-use plugins (never invoked by ``run``)."""
    from eglk_harness.domain.plugins import (
        COMMUNITY_PLUGINS,
        COMPUTER_USE_PLUGIN_ID,
        PLUGIN_PRIORITY,
        PluginError,
        active_plugin_for_agent,
        community_plugin_ids,
        community_plugin_state,
        get_codex_plugin_state,
        get_community_plugin,
        install_community_plugin,
        install_computer_use_plugin,
        npm_binary,
        plugins_root,
        uninstall_community_plugin,
        uninstall_computer_use_plugin,
    )

    assert set(_PLUGIN_CHOICES) == {_CODEX_GUI_PLUGIN, *community_plugin_ids()}

    action = getattr(args, "plugin_command", None)
    if not action:
        print("usage: eglk-harness plugin {list,install,uninstall} ...", flush=True)
        return 2
    if action == "list":
        print(f"Priority when several are installed: {' > '.join(PLUGIN_PRIORITY)}")
        print(f"Generated MCP configs live under {plugins_root()}")
        for agent in ("codex", "claude_code"):
            try:
                active = active_plugin_for_agent(agent)
            except PluginError as exc:
                print(f"Active for {agent}: unknown ({exc})")
            else:
                print(f"Active for {agent}: {active[0] if active else 'none installed'}")
        try:
            official = get_codex_plugin_state(COMPUTER_USE_PLUGIN_ID)
            if official.ready:
                state = f"installed and enabled {official.version}".strip()
            elif official.installed:
                state = "installed but disabled"
            elif official.available:
                state = "not installed"
            else:
                state = "unavailable on this Codex build"
        except (PluginError, CodexPluginError) as exc:
            state = f"unknown ({exc})"
        print(f"\n{_CODEX_GUI_PLUGIN}")
        print("  Official Codex Computer Use (bundled with Codex CLI).")
        print(f"  state : {state}")
        npm_missing = not npm_binary()
        for plugin in COMMUNITY_PLUGINS:
            if npm_missing:
                pstate = "unknown (npm missing; needs Node.js 20+)"
            else:
                try:
                    pkg = community_plugin_state(plugin)
                    pstate = (
                        f"installed {pkg.version}".strip()
                        if pkg.installed
                        else "not installed"
                    )
                except PluginError as exc:
                    pstate = f"unknown ({exc})"
            print(f"\n{plugin.plugin_id}")
            print(f"  {plugin.summary}")
            print(f"  state : {pstate}")
            print(f"  homepage : {plugin.homepage}")
        return 0

    name = getattr(args, "name", None)
    if not name:
        print("plugin install/uninstall requires --name", flush=True)
        return 2
    try:
        if name == _CODEX_GUI_PLUGIN:
            if action == "install":
                state = install_computer_use_plugin(
                    on_status=lambda s, m: _doctor_line("…. ", s, m),
                )
                _doctor_line(
                    "ok",
                    name,
                    f"ready={state.ready} installed={state.installed} enabled={state.enabled}",
                )
                return 0 if state.ready else 1
            if action == "uninstall":
                state = uninstall_computer_use_plugin(
                    on_status=lambda s, m: _doctor_line("…. ", s, m),
                )
                _doctor_line("ok", name, f"installed={state.installed}")
                return 0
            print(f"unknown plugin action: {action}", flush=True)
            return 2
        plugin = get_community_plugin(name)
        agents = list(args.agent) if getattr(args, "agent", None) else list(plugin.agents)
        if action == "install":
            install_community_plugin(
                plugin,
                agents=agents,
                on_status=lambda s, m: _doctor_line("…. ", s, m),
                activate=not bool(getattr(args, "skip_activation", False)),
            )
            _doctor_line("ok", name, f"installed for agents={agents}")
            return 0
        if action == "uninstall":
            uninstall_community_plugin(
                plugin,
                on_status=lambda s, m: _doctor_line("…. ", s, m),
            )
            _doctor_line("ok", name, "uninstalled")
            return 0
        print(f"unknown plugin action: {action}", flush=True)
        return 2
    except (PluginError, CodexPluginError) as exc:
        _doctor_line("FAIL", name, str(exc))
        return 1

def _cmd_doctor(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    code = 0
    as_json = bool(getattr(args, "json", False))
    gui_detail: str | None = None
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
                gui_detail = f"{state.plugin_id} is not installed"
                if not as_json:
                    _doctor_line("ok", "Codex GUI", gui_detail)
            elif state.ready:
                ver = f" v{state.version}" if state.version else ""
                gui_detail = f"{state.plugin_id}{ver} is installed and enabled"
                if not as_json:
                    _doctor_line("ok", "Codex GUI", gui_detail)
            else:
                gui_detail = f"{state.plugin_id} installed={state.installed} enabled={state.enabled}"
                if not as_json:
                    _doctor_line("FAIL", "Codex GUI", gui_detail)
                code = 1
        except CodexPluginError as exc:
            if as_json:
                print(json.dumps({"ok": False, "error": str(exc), "read_only": True, "hitl": False}))
            else:
                _doctor_line("FAIL", "Codex GUI", str(exc))
            return 2
    else:
        try:
            state = get_codex_plugin_state(COMPUTER_USE_PLUGIN_ID)
            if state.ready:
                ver = f" v{state.version}" if state.version else ""
                gui_detail = f"{state.plugin_id}{ver} ready"
                if not as_json:
                    _doctor_line("ok", "Codex GUI", gui_detail)
            elif state.available:
                gui_detail = (
                    f"{state.plugin_id} available but not ready; "
                    "run `eglk-harness doctor --install-codex-gui`"
                )
                if not as_json:
                    _doctor_line("WARN", "Codex GUI", gui_detail)
            else:
                gui_detail = f"{state.plugin_id} unavailable"
                if not as_json:
                    _doctor_line("WARN", "Codex GUI", gui_detail)
        except CodexPluginError as exc:
            gui_detail = str(exc)
            if not as_json:
                _doctor_line("WARN", "Codex GUI", gui_detail)

    report = run_doctor(workdir)
    if gui_detail is not None:
        from eglk_harness.domain.product.doctor import DoctorCheck

        report.checks.append(DoctorCheck(name="codex_gui", ok=True, detail=gui_detail))
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0 if report.ok and code == 0 else 1
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
        if not c.ok:
            code = 1
    return code

def _cmd_run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    from eglk_harness.domain.product.runtime_bootstrap import (
        bootstrap_workdir,
        soft_max_ticks,
        want_dashboard,
    )

    cli_env: dict[str, str] = {}
    if args.maker_model:
        cli_env["EGLK_MODEL_MAKER"] = args.maker_model
    if args.checker_model:
        cli_env["EGLK_MODEL_CHECKER"] = args.checker_model
    if args.model:
        cli_env["EGLK_MODEL"] = args.model
        if not args.maker_model:
            cli_env["EGLK_MODEL_MAKER"] = args.model
        if not args.checker_model:
            cli_env["EGLK_MODEL_CHECKER"] = args.model
    if args.mcp_config:
        cli_env["EGLK_MCP_CONFIG"] = str(Path(args.mcp_config).resolve())
    bootstrap_workdir(workdir, cli_env=cli_env)

    kwargs: dict = {
        "workdir": workdir,
        "goal": args.goal,
        "agent": resolve_agent(args.agent, workdir),
        "swarm": resolve_swarm(args.swarm, workdir),
        "mcp_config": Path(args.mcp_config) if args.mcp_config else None,
        "mcp_add_dirs": list(args.mcp_add_dir or []),
        "compile": resolve_compile(args.compile, workdir),
        "maker_timeout_s": args.maker_timeout,
        "checker_timeout_s": args.checker_timeout,
    }
    from eglk_harness.domain.runtime.budgets import resolve_role_budgets

    budgets = resolve_role_budgets(args)
    if kwargs["maker_timeout_s"] is None:
        kwargs["maker_timeout_s"] = budgets.maker.max_duration_seconds
    if kwargs["checker_timeout_s"] is None:
        kwargs["checker_timeout_s"] = budgets.checker.max_duration_seconds
    os.environ.setdefault(
        "EGLK_TIMEOUT_GOVERNOR", str(budgets.governor.max_duration_seconds)
    )
    os.environ.setdefault(
        "EGLK_TIMEOUT_EXPLORER", str(budgets.explorer.max_duration_seconds)
    )
    os.environ.setdefault(
        "EGLK_TIMEOUT_VERIFIER", str(budgets.verifier.max_duration_seconds)
    )
    os.environ.setdefault(
        "EGLK_TIMEOUT_REFINER", str(budgets.refiner.max_duration_seconds)
    )
    ticks = soft_max_ticks(args.max_ticks)
    if ticks is not None:
        kwargs["max_ticks"] = ticks
    if getattr(args, "tick", None) is not None:
        kwargs["tick"] = args.tick
    code = app_run(RunRequest(**kwargs))
    open_dash = bool(getattr(args, "dashboard", False)) or want_dashboard(cli_flag=None)
    if open_dash:
        port = int(getattr(args, "dashboard_port", 8766) or 8766)
        print(
            f"opening read-only dashboard on http://127.0.0.1:{port}/ (Ctrl+C to stop)",
            flush=True,
        )
        serve_dashboard(workdir, host="127.0.0.1", port=port, blocking=True)
    return code

def _cmd_status(args: argparse.Namespace) -> int:
    report = collect_status(Path(args.workdir).resolve(), run_id=args.run)
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(report.render())
    return 0

def _cmd_check_projections(args: argparse.Namespace) -> int:
    report = check_projections()
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0 if report.ok else 1
    for c in report.checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"{mark}  {c.name}: {c.detail}")
    return 0 if report.ok else 1

def _cmd_soak_bypass(args: argparse.Namespace) -> int:
    import asyncio

    from eglk_harness.domain.adapters.factory import create_adapter
    from eglk_harness.domain.eval.bypass_soak import soak_bypass_roles

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

def _cmd_check_update(args: argparse.Namespace) -> int:
    result = check_update()
    if getattr(args, "json", False):
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
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

def _emit_eval_scores(
    *,
    workdir: Path,
    suite: str,
    task_id: str,
    agent: str,
    swarm: str | None,
    scores: dict,
    ok: bool,
    detail: str,
) -> int:
    """Write Manifest with offline scores (never Gate inputs); print JSON + note."""
    scores.setdefault("task_id", task_id)
    scores.setdefault("workdir", str(workdir))
    run_id = new_run_id("eval")
    manifest = build_manifest(
        run_id=run_id,
        workdir=workdir,
        goal_id=f"eval-{suite}-{task_id}",
        agent=str(agent),
        model=resolve_model("maker"),
        swarm=swarm,
        extra={"scores": scores, "eval_ok": ok, "eval_detail": detail},
    )
    path = write_manifest(workdir, manifest)
    print(json.dumps({"eval": scores, "ok": ok, "detail": detail, "manifest": str(path)}, indent=2))
    print("note: offline scores are Manifest-only — never Gate inputs")
    return 0 if ok else 1

def _cmd_eval(args: argparse.Namespace) -> int:
    eval_root = Path(args.eval_root).resolve() if args.eval_root else default_eval_root()
    if eval_root is None or not eval_root.is_dir():
        print(
            "error: eval root not found; set EGLK_EVAL_ROOT to experiment/eval. "
            "Scorers never feed Gate.",
            flush=True,
        )
        return 2

    if getattr(args, "list_tasks", False):
        rows: list[dict[str, str]] = []
        if args.suite == "wa_hard":
            wa_hard_mod = _suite_mod("wa_hard", eval_root)
            rows = [{"id": t.task_id, "summary": t.intent} for t in wa_hard_mod.load_pack_index(eval_root)]
        elif args.suite == "osworld_aux":
            osworld_mod = _suite_mod("osworld_aux", eval_root)
            rows = [
                {"id": t.task_id, "summary": t.instruction}
                for t in osworld_mod.load_pack_index(eval_root)
            ]
        elif args.suite == "weave_lh":
            weave_lh_mod = _suite_mod("weave_lh", eval_root)
            rows = [
                {"id": t.task_id, "summary": t.summary} for t in weave_lh_mod.load_pack_index(eval_root)
            ]
        elif args.suite == "tb21":
            tb21_mod = _suite_mod("tb21", eval_root)
            rows = [
                {"id": t.task_id, "summary": t.summary} for t in tb21_mod.load_pack_index(eval_root)
            ]
        elif args.suite == "weave_thin":
            tasks_path = eval_root / "weave_thin" / "tasks.example.json"
            if tasks_path.is_file():
                data = json.loads(tasks_path.read_text(encoding="utf-8"))
                tasks = data.get("tasks") if isinstance(data, dict) else data
                if isinstance(tasks, list):
                    for t in tasks:
                        if isinstance(t, dict) and t.get("id"):
                            rows.append(
                                {
                                    "id": str(t["id"]),
                                    "summary": str(t.get("summary") or t.get("title") or ""),
                                }
                            )
        print(json.dumps({"suite": args.suite, "count": len(rows), "tasks": rows}, indent=2))
        print("note: listing only — scorers never feed Gate")
        return 0

    out = Path(args.workdir).resolve()

    if getattr(args, "batch", False):
        if args.suite != "wa_hard":
            print("error: --batch currently supports --suite wa_hard only", flush=True)
            return 2
        limit = int(args.limit) if getattr(args, "limit", None) is not None else None
        external = Path(args.external_score).resolve() if getattr(args, "external_score", None) else None
        agent_runs = (
            Path(args.score_agent_runs).resolve() if getattr(args, "score_agent_runs", None) else None
        )
        if agent_runs is not None and not args.prepare_only:
            wa_hard_mod = _suite_mod("wa_hard", eval_root)
            # Prefer official agent-run ingest over placeholder when scoring a batch.
            summary = wa_hard_mod.run_batch(
                eval_root,
                out_root=out,
                limit=limit,
                prepare_only=False,
                external_score_dir=None,
            )
            ingested = wa_hard_mod.ingest_agent_runs(agent_runs)
            by_id = {r["task_id"]: r for r in ingested.get("tasks") or []}
            for entry in summary.get("tasks") or []:
                row = by_id.get(str(entry.get("task_id")))
                if row:
                    entry["scores"] = row.get("scores")
                    entry["detail"] = row.get("detail")
                    entry["ok"] = bool(row.get("ok"))
            summary["agent_runs"] = ingested
            summary["note"] = "official agent-run scores — Manifest-only; never Gate"
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            print("note: offline scores are Manifest-only — never Gate inputs")
            return 0 if ingested.get("ok") else 1
        wa_hard_mod = _suite_mod("wa_hard", eval_root)
        summary = wa_hard_mod.run_batch(
            eval_root,
            out_root=out,
            limit=limit,
            prepare_only=bool(args.prepare_only),
            external_score_dir=external,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print("note: offline scores are Manifest-only — never Gate inputs")
        return 0

    if not args.task_id:
        print("error: --task-id required unless --batch or --list-tasks", flush=True)
        return 2

    wa_hard_mod = osworld_mod = weave_lh_mod = tb21_mod = None
    if args.suite == "wa_hard":
        wa_hard_mod = _suite_mod("wa_hard", eval_root)
    elif args.suite == "osworld_aux":
        osworld_mod = _suite_mod("osworld_aux", eval_root)
    elif args.suite == "weave_lh":
        weave_lh_mod = _suite_mod("weave_lh", eval_root)
    elif args.suite == "tb21":
        tb21_mod = _suite_mod("tb21", eval_root)

    if args.suite == "wa_hard":
        tasks = {t.task_id: t for t in wa_hard_mod.load_pack_index(eval_root)}
        task = tasks.get(args.task_id)
        if task is None and getattr(args, "score_agent_runs", None):
            # Official demo / external agent-run ids need not be in Hard pack.
            task = wa_hard_mod.WaHardTask(
                task_id=str(args.task_id),
                intent=f"External/official agent-run score for {args.task_id}",
                sites=[],
                notes="score-agent-runs only — Manifest; never Gate",
            )
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
    elif args.suite == "weave_lh":
        tasks = {t.task_id: t for t in weave_lh_mod.load_pack_index(eval_root)}
        task = tasks.get(args.task_id)
        if task is None:
            print(f"error: unknown weave_lh task_id={args.task_id}", flush=True)
            return 2
        weave_lh_mod.materialize_goal(task, out)
    elif args.suite == "tb21":
        tasks = {t.task_id: t for t in tb21_mod.load_pack_index(eval_root)}
        task = tasks.get(args.task_id)
        if task is None:
            print(f"error: unknown tb21 task_id={args.task_id}", flush=True)
            return 2
        tb21_mod.materialize_goal(task, out)
    else:
        prepare_task_workdir(eval_root, suite=args.suite, task_id=args.task_id, out_dir=out)
    init_project(out)
    print(f"prepared eval workdir {out} suite={args.suite} task={args.task_id}")
    if args.prepare_only:
        if args.suite == "wa_hard" and getattr(args, "score_agent_runs", None):
            runs = Path(args.score_agent_runs)
            cand = runs / str(args.task_id) / "eval_result.json"
            if not cand.is_file() and (runs / "eval_result.json").is_file():
                cand = runs / "eval_result.json"
            if not cand.is_file():
                print(f"error: missing eval_result.json under {runs} for task {args.task_id}", flush=True)
                return 2
            scores = wa_hard_mod.score_from_eval_result(cand)
            ok = bool(float(scores.get("success") or 0) >= 1.0)
            return _emit_eval_scores(
                workdir=out,
                suite=args.suite,
                task_id=args.task_id,
                agent=args.agent,
                swarm=args.swarm,
                scores=scores,
                ok=ok,
                detail="official_scored",
            )
        if args.suite == "wa_hard" and getattr(args, "score_har", None):
            scores = wa_hard_mod.score_har_offline(Path(args.score_har))
            ok = bool(float(scores.get("success") or 0) >= 1.0)
            return _emit_eval_scores(
                workdir=out,
                suite=args.suite,
                task_id=args.task_id,
                agent=args.agent,
                swarm=args.swarm,
                scores=scores,
                ok=ok,
                detail="har_offline_scored",
            )
        if args.suite == "weave_lh" and getattr(args, "external_score", None):
            scores = weave_lh_mod.score_from_judge_result(Path(args.external_score))
            ok = bool(float(scores.get("success") or scores.get("pass") or 0) >= 1.0) or scores.get(
                "status"
            ) == "external_scored"
            return _emit_eval_scores(
                workdir=out,
                suite=args.suite,
                task_id=args.task_id,
                agent=args.agent,
                swarm=args.swarm,
                scores=scores,
                ok=ok,
                detail="weave_lh_external",
            )
        if args.suite == "osworld_aux" and getattr(args, "external_score", None):
            scores = osworld_mod.score_external(Path(args.external_score))
            return _emit_eval_scores(
                workdir=out,
                suite=args.suite,
                task_id=args.task_id,
                agent=args.agent,
                swarm=args.swarm,
                scores=scores,
                ok=True,
                detail="osworld_external",
            )
        if args.suite == "tb21" and getattr(args, "external_score", None):
            scores = tb21_mod.score_from_judge_result(Path(args.external_score))
            ok = bool(float(scores.get("success") or scores.get("pass") or 0) >= 1.0) or scores.get(
                "status"
            ) == "external_scored"
            return _emit_eval_scores(
                workdir=out,
                suite=args.suite,
                task_id=args.task_id,
                agent=args.agent,
                swarm=args.swarm,
                scores=scores,
                ok=ok,
                detail="tb21_external",
            )
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
        if getattr(args, "score_agent_runs", None):
            runs = Path(args.score_agent_runs)
            cand = runs / str(args.task_id) / "eval_result.json"
            if not cand.is_file() and (runs / "eval_result.json").is_file():
                cand = runs / "eval_result.json"
            if cand.is_file():
                scores = wa_hard_mod.score_from_eval_result(cand)
                ok = bool(float(scores.get("success") or 0) >= 1.0)
                detail = "official_scored"
            else:
                scores = wa_hard_mod.score_placeholder(task_id=args.task_id, workdir=out)
                ok = False
                detail = "missing_eval_result"
        elif getattr(args, "score_har", None):
            scores = wa_hard_mod.score_har_offline(Path(args.score_har))
            ok = bool(float(scores.get("success") or 0) >= 1.0)
            detail = "har_offline_scored"
        elif getattr(args, "external_score", None):
            scores = wa_hard_mod.score_external(Path(args.external_score))
            ok = True
            detail = "external_scored"
        else:
            scores = wa_hard_mod.score_placeholder(task_id=args.task_id, workdir=out)
            ok = True
            detail = "recorded_only"
    elif args.suite == "osworld_aux":
        if getattr(args, "external_score", None):
            scores = osworld_mod.score_external(Path(args.external_score))
            ok = True
            detail = "external_scored"
        else:
            scores = osworld_mod.score_placeholder(task_id=args.task_id, workdir=out, eval_root=eval_root)
            ok = True
            detail = "recorded_only"
        hint = osworld_mod.path_hint(eval_root)
        if hint is not None:
            scores["vendor_hint"] = str(hint)
    elif args.suite == "weave_lh":
        if getattr(args, "external_score", None):
            scores = weave_lh_mod.score_from_judge_result(Path(args.external_score))
            ok = True
            detail = "external_scored"
        else:
            scores = weave_lh_mod.score_placeholder(
                task_id=args.task_id, workdir=out, eval_root=eval_root
            )
            ok = True
            detail = scores.get("status") or "recorded_only"
    elif args.suite == "tb21":
        if getattr(args, "external_score", None):
            scores = tb21_mod.score_from_judge_result(Path(args.external_score))
            ok = True
            detail = "external_scored"
        else:
            scores = tb21_mod.score_placeholder(
                task_id=args.task_id, workdir=out, eval_root=eval_root
            )
            ok = True
            detail = scores.get("status") or "recorded_only"
    else:
        scored = score_offline(
            suite=args.suite, task_id=args.task_id, workdir=out, eval_root=eval_root
        )
        scores, ok, detail = scored.scores, scored.ok, scored.detail
    eval_rc = _emit_eval_scores(
        workdir=out,
        suite=args.suite,
        task_id=args.task_id,
        agent=args.agent,
        swarm=args.swarm,
        scores=scores,
        ok=ok,
        detail=detail,
    )
    return rc if rc else eval_rc

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
        "--json",
        action="store_true",
        help="Machine-readable JSON (still read-only; never installs)",
    )
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

    plug = sub.add_parser("plugin", help="Install or remove computer-use plugins (never by run)")
    plug_sub = plug.add_subparsers(dest="plugin_command")
    for action, help_text in (
        ("list", "Show available computer-use plugins and install state"),
        ("install", "Install a computer-use plugin and register it with an agent"),
        ("uninstall", "Remove a computer-use plugin"),
    ):
        sp = plug_sub.add_parser(action, help=help_text)
        if action != "list":
            sp.add_argument(
                "--name",
                required=True,
                choices=_PLUGIN_CHOICES,
                help="Plugin id (see `eglk-harness plugin list`)",
            )
        if action == "install":
            sp.add_argument(
                "--agent",
                action="append",
                choices=("codex", "claude_code"),
                help="Agent to register (repeatable; default: all supported)",
            )
            sp.add_argument(
                "--skip-activation",
                action="store_true",
                help="Skip consent / OS-permission commands",
            )
        sp.set_defaults(func=_cmd_plugin)
    plug.set_defaults(func=_cmd_plugin)

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
        help="Extra readable dir for role MCP sessions (repeatable; filtered by allowlist)",
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
    run_p.add_argument(
        "--dashboard",
        action="store_true",
        help="After run, open read-only dashboard (never an approval gate)",
    )
    run_p.add_argument(
        "--dashboard-port",
        type=int,
        default=8766,
        help="Port for --dashboard (default 8766)",
    )
    run_p.set_defaults(func=_cmd_run)

    st_p = sub.add_parser("status", help="Read-only status of harness dirs / runs")
    st_p.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    st_p.add_argument("--run", default=None, help="Select loop/<run_id> (default: newest)")
    st_p.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON (still read-only; never an approval surface)",
    )
    st_p.set_defaults(func=_cmd_status)

    dash = sub.add_parser("dashboard", help="Read-only HTTP dashboard (never an approval gate)")
    dash.add_argument("--workdir", default=".", help="Project root (default: cwd)")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8766)
    dash.set_defaults(func=_cmd_dashboard)

    cu = sub.add_parser("check-update", help="Check PyPI for a newer eglk-harness (no auto-upgrade)")
    cu.add_argument("--json", action="store_true", help="Machine-readable JSON (never auto-upgrades)")
    cu.set_defaults(func=_cmd_check_update)

    ev = sub.add_parser(
        "eval",
        help="Auxiliary eval suite runner (offline scores never feed Gate)",
    )
    ev.add_argument(
        "--suite",
        required=True,
        choices=sorted(eval_suite_choices()),
    )
    ev.add_argument("--task-id", default=None, help="Single task id (required unless --batch)")
    ev.add_argument("--eval-root", default=None, help="Eval pack root (default: bundled or EGLK_EVAL_ROOT)")
    ev.add_argument("--workdir", default="./.eglk-eval-workdir", help="Materialized task workdir")
    ev.add_argument("--agent", default="mock", choices=("mock", "codex", "claude_code"))
    ev.add_argument("--swarm", default="0")
    ev.add_argument("--compile", default="off", choices=("auto", "force", "off"))
    ev.add_argument("--max-ticks", type=int, default=4)
    ev.add_argument("--prepare-only", action="store_true", help="Only write .goal.md / init")
    ev.add_argument(
        "--list-tasks",
        action="store_true",
        help="List task ids for --suite (no run; scorers never Gate)",
    )
    ev.add_argument(
        "--batch",
        action="store_true",
        help="Batch mode for wa_hard (writes batch_summary.json under --workdir)",
    )
    ev.add_argument("--limit", type=int, default=None, help="Max tasks in --batch")
    ev.add_argument(
        "--external-score",
        default=None,
        help="Path to external judge JSON (wa_hard); or directory of <task_id>.json for --batch",
    )
    ev.add_argument(
        "--score-har",
        default=None,
        help="Path to eglk_wa_trace JSON (HAR-offline stand-in); Manifest-only — never Gate",
    )
    ev.add_argument(
        "--score-agent-runs",
        default=None,
        help=(
            "WA-Hard: directory of <task_id>/eval_result.json from official eval-tasks "
            "(Manifest-only — never Gate)"
        ),
    )
    ev.set_defaults(func=_cmd_eval)

    cp = sub.add_parser(
        "check-projections",
        help="CI pin: assert thresholds match packaged projection constants",
    )
    cp.add_argument("--json", action="store_true", help="Machine-readable JSON")
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
