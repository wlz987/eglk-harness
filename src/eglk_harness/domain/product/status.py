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
    decision_count: int = 0
    tick: int | None = None
    focus_score: float | None = None
    uncertainty: float | None = None
    quota: dict[str, Any] = field(default_factory=dict)
    leaf_contract: dict[str, Any] | None = None
    last_tick: dict[str, Any] | None = None
    sigma_active_count: int = 0
    run_status: str | None = None
    run_status_reason: str | None = None
    events_db_present: bool = False
    events_hash_chain_ok: bool = False
    last_sequence: int | None = None
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
                f"  (n={self.decision_count})"
            )
        else:
            lines.append(f"decision:    (none)  (n={self.decision_count})")

        if self.tick is not None:
            proj = []
            if self.focus_score is not None:
                proj.append(f"focus={self.focus_score}")
            if self.uncertainty is not None:
                proj.append(f"unc={self.uncertainty}")
            extra = f"  {' '.join(proj)}" if proj else ""
            lines.append(f"tick:        {self.tick}{extra}  (τ_focus/τ_unc signal only — never abort)")

        q = self.quota
        lines.append(
            "quota:       "
            f"cognitive_tokens={q.get('cognitive_tokens', 0)}/"
            f"{q.get('cognitive_tokens_max', P.COGNITIVE_TOKENS_MAX)}  "
            f"repairs_max={q.get('repairs_max', P.REPAIRS_MAX)}  "
            f"usd_used={q.get('usd_used', 0)}"
        )
        lines.append(f"sigma.active: {self.sigma_active_count}")
        if self.run_status:
            extra = f" ({self.run_status_reason})" if self.run_status_reason else ""
            lines.append(f"run:         {self.run_status}{extra}")
        if self.events_db_present:
            chain = "ok" if self.events_hash_chain_ok else "BROKEN"
            seq = self.last_sequence if self.last_sequence is not None else "?"
            lines.append(f"events.db:   present  hash_chain={chain}  last_seq={seq}")

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

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable snapshot — still read-only; never an approval surface."""
        return {
            "workdir": str(self.workdir),
            "harness_present": self.harness_present,
            "goal_present": self.goal_present,
            "goal_format_present": self.goal_format_present,
            "runs": list(self.runs),
            "selected_run": self.selected_run,
            "tree": list(self.tree_summary),
            "latest_decision": self.latest_decision,
            "decision_count": self.decision_count,
            "tick": self.tick,
            "focus_score": self.focus_score,
            "uncertainty": self.uncertainty,
            "quota": dict(self.quota),
            "leaf_contract": self.leaf_contract,
            "last_tick": self.last_tick,
            "sigma_active_count": self.sigma_active_count,
            "run_status": self.run_status,
            "run_status_reason": self.run_status_reason,
            "events_db_present": self.events_db_present,
            "events_hash_chain_ok": self.events_hash_chain_ok,
            "last_sequence": self.last_sequence,
            "notes": list(self.notes),
            "read_only": True,
            "hitl": False,
        }

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
    # Prefer config/env effective max so status matches run bootstrap before projections exist.
    try:
        from eglk_harness.domain.product.config_resolve import load_config_toml

        cfg = load_config_toml(workdir)
        limits = cfg.get("limits") if isinstance(cfg.get("limits"), dict) else {}
        cog_max = P.effective_cognitive_tokens_max()
        if limits.get("cognitive_tokens_max") is not None:
            cog_max = int(limits["cognitive_tokens_max"])
        repairs_max = P.effective_repairs_max()
        if limits.get("repairs_max") is not None:
            repairs_max = int(limits["repairs_max"])
    except (TypeError, ValueError, OSError):
        cog_max = P.effective_cognitive_tokens_max()
        repairs_max = P.effective_repairs_max()

    report = StatusReport(
        workdir=workdir,
        harness_present=paths.harness_root(workdir).is_dir(),
        goal_present=paths.goal_path(workdir).is_file(),
        goal_format_present=(workdir / ".goal_format.md").is_file(),
        quota={
            "cognitive_tokens": 0,
            "cognitive_tokens_max": cog_max,
            "repairs_max": repairs_max,
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
    from eglk_harness.domain.kernel.projection_read import (
        events_summary,
        read_run_projection,
        read_task_structure,
    )

    rp = read_run_projection(workdir, selected)
    if rp:
        report.run_status = str(rp.get("run_status") or "") or None
        report.run_status_reason = rp.get("run_status_reason")
        if rp.get("last_sequence") is not None:
            try:
                report.last_sequence = int(rp["last_sequence"])
            except (TypeError, ValueError):
                pass
        if isinstance(rp.get("quota"), dict):
            report.quota.update(rp["quota"])

    evs = events_summary(workdir, selected)
    report.events_db_present = bool(evs.get("present"))
    report.events_hash_chain_ok = bool(evs.get("hash_chain_ok"))
    if evs.get("last_sequence") is not None and report.last_sequence is None:
        try:
            report.last_sequence = int(evs["last_sequence"])
        except (TypeError, ValueError):
            pass
    if evs.get("error"):
        report.notes.append(f"events.db: {evs['error']}")

    ts_doc = read_task_structure(workdir, selected)
    if ts_doc and isinstance(ts_doc.get("root"), dict):
        def _walk_tree(node: dict[str, Any], depth: int = 0) -> None:
            report.tree_summary.append(
                {
                    "id": node.get("id"),
                    "title": node.get("title"),
                    "status": node.get("status"),
                    "repair_streak": 0,
                    "depth": depth,
                }
            )
            for ch in node.get("children") or []:
                if isinstance(ch, dict):
                    _walk_tree(ch, depth + 1)

        if not report.tree_summary:
            _walk_tree(ts_doc["root"])

    decision = _latest_json(loop_dir / "decisions")
    if decision:
        report.latest_decision = decision
    dec_dir = loop_dir / "decisions"
    if dec_dir.is_dir():
        report.decision_count = sum(1 for _ in dec_dir.glob("*.json"))

    had_projection_quota = bool(rp and isinstance(rp.get("quota"), dict))
    if had_projection_quota:
        report.tick = report.last_sequence if report.last_sequence is not None else report.tick

    report.last_tick = _last_jsonl(loop_dir / "ticks.jsonl")
    if report.last_tick and isinstance(report.last_tick.get("quota"), dict):
        report.quota.update(report.last_tick["quota"])
    if report.last_tick and report.last_tick.get("focus_score") is not None:
        try:
            report.focus_score = float(report.last_tick["focus_score"])
        except (TypeError, ValueError):
            pass
    if report.last_tick and report.last_tick.get("uncertainty") is not None:
        try:
            report.uncertainty = float(report.last_tick["uncertainty"])
        except (TypeError, ValueError):
            pass
    if report.tick is None and report.last_tick and report.last_tick.get("tick") is not None:
        try:
            report.tick = int(report.last_tick["tick"])
        except (TypeError, ValueError):
            pass

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
