"""Read-only run status (never an approval / HITL gate)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eglk_harness.domain.kernel import loop_store
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.memory import sigma
from eglk_harness.domain.kernel import projections as P


@dataclass
class StatusReport:
    workdir: Path
    harness_present: bool
    goal_present: bool
    goal_format_present: bool
    runs: list[str] = field(default_factory=list)
    selected_run: str | None = None
    tree_summary: list[dict[str, Any]] = field(default_factory=list)
    latest_decision: dict[str, Any] | None = None
    quota: dict[str, Any] = field(default_factory=dict)
    leaf_contract: dict[str, Any] | None = None
    last_tick: dict[str, Any] | None = None
    sigma_active_count: int = 0
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"workdir:     {self.workdir}",
            f"harness:     {paths.harness_root(self.workdir)}  ({'yes' if self.harness_present else 'no'})",
            f"goal:        {paths.goal_path(self.workdir)}  ({'yes' if self.goal_present else 'no'})",
            f"goal_format: {(self.workdir / '.goal_format.md')}  ({'yes' if self.goal_format_present else 'no'})",
            f"runs:        {', '.join(self.runs) if self.runs else '(none)'}",
        ]
        if self.selected_run:
            lines.append(f"selected:    {self.selected_run}")
        if self.tree_summary:
            lines.append("tree:")
            for n in self.tree_summary:
                streak = n.get("repair_streak") or 0
                extra = f"  repair_streak={streak}" if streak else ""
                lines.append(f"  - {n['id']}: {n['status']}{extra}  ({n.get('title', '')})")
        else:
            lines.append("tree:        (none)")

        if self.latest_decision:
            d = self.latest_decision
            lines.append(
                f"decision:    {d.get('decision')} ({d.get('reason')})  tick={d.get('tick')}"
            )
        else:
            lines.append("decision:    (none)")

        q = self.quota
        lines.append(
            "quota:       "
            f"cognitive_tokens={q.get('cognitive_tokens', 0)}/"
            f"{q.get('cognitive_tokens_max', P.COGNITIVE_TOKENS_MAX)}  "
            f"repairs_max={q.get('repairs_max', P.REPAIRS_MAX)}  "
            f"usd_used={q.get('usd_used', 0)}"
        )
        lines.append(f"sigma.active: {self.sigma_active_count}")

        if self.leaf_contract:
            lc = self.leaf_contract
            acc = lc.get("acceptance") or []
            lines.append(
                f"leaf:        id={lc.get('leaf_id')}  "
                f"acceptance={len(acc)}  tick={lc.get('tick')}"
            )
            for a in acc[:5]:
                lines.append(f"               - {a}")
        else:
            lines.append("leaf:        (none)")

        if self.last_tick:
            sw = self.last_tick.get("swarm_enabled") or {}
            lines.append(
                f"last_tick:   tick={self.last_tick.get('tick')}  "
                f"swarm_explorer={sw.get('explorer')}  "
                f"sigma_merged={self.last_tick.get('sigma_merged')}"
            )

        lines.append("(status is read-only; no approval controls)")
        for note in self.notes:
            lines.append(f"note:        {note}")
        return "\n".join(lines)


def _latest_json(dir_path: Path) -> dict[str, Any] | None:
    if not dir_path.is_dir():
        return None
    files = sorted(dir_path.glob("*.json"))
    if not files:
        return None
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _last_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            last = obj
    return last


def _leaf_from_reasoning(loop_dir: Path) -> dict[str, Any] | None:
    log = loop_dir / "reasoning_log.jsonl"
    if not log.is_file():
        return None
    found: dict[str, Any] | None = None
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if str(obj.get("file", "")).startswith("leaf_contract_"):
            payload = obj.get("payload")
            if isinstance(payload, dict):
                found = payload
    return found


def _pick_run(loop_root: Path, prefer: str | None) -> str | None:
    if not loop_root.is_dir():
        return None
    runs = [p for p in loop_root.iterdir() if p.is_dir()]
    if not runs:
        return None
    if prefer and (loop_root / prefer).is_dir():
        return prefer
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0].name


def collect_status(workdir: Path, *, run_id: str | None = None) -> StatusReport:
    """Assemble a read-only snapshot. Never mutates harness state."""
    workdir = workdir.resolve()
    report = StatusReport(
        workdir=workdir,
        harness_present=paths.harness_root(workdir).is_dir(),
        goal_present=paths.goal_path(workdir).is_file(),
        goal_format_present=(workdir / ".goal_format.md").is_file(),
        quota={
            "cognitive_tokens": 0,
            "cognitive_tokens_max": P.COGNITIVE_TOKENS_MAX,
            "repairs_max": P.REPAIRS_MAX,
        },
    )
    loop_root = paths.loop_root(workdir)
    if loop_root.is_dir():
        report.runs = sorted(p.name for p in loop_root.iterdir() if p.is_dir())

    selected = _pick_run(loop_root, run_id)
    report.selected_run = selected
    if not selected:
        report.notes.append("no loop run yet — run `eglk-harness run`")
        return report

    loop_dir = loop_root / selected
    tree = loop_store.load_tree(loop_dir)
    if tree is not None:
        for node, _depth in tree.walk():
            report.tree_summary.append(
                {
                    "id": node.id,
                    "title": node.title,
                    "status": node.status,
                    "repair_streak": node.repair_streak,
                }
            )

    decision = _latest_json(loop_dir / "decisions")
    if decision:
        report.latest_decision = decision

    state_path = loop_dir / "state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(state, dict) and isinstance(state.get("quota"), dict):
                report.quota.update(state["quota"])
        except (OSError, json.JSONDecodeError):
            pass

    report.last_tick = _last_jsonl(loop_dir / "ticks.jsonl")
    if report.last_tick and isinstance(report.last_tick.get("quota"), dict):
        report.quota.update(report.last_tick["quota"])

    report.leaf_contract = _leaf_from_reasoning(loop_dir)
    if report.leaf_contract is None:
        cand = loop_dir / "candidates"
        for path in sorted(cand.glob("leaf_contract_*.json")) if cand.is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                report.leaf_contract = data
                break

    report.sigma_active_count = len(sigma.load_active(workdir))
    try:
        from eglk_harness.domain.adapters.mcp import resolve_mcp_config
        from eglk_harness.domain.plugins.state import active_plugin_for_agent

        mcp = resolve_mcp_config(None)
        if mcp is not None:
            report.notes.append(f"mcp={mcp}")
        for agent in ("codex", "claude_code"):
            active = active_plugin_for_agent(agent)
            if active:
                report.notes.append(f"plugin[{agent}]={active[0]}")
    except Exception:
        pass
    return report
