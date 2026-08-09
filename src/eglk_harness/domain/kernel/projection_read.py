"""Read run status from event projections (preferred) with legacy fallbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.event_store import open_store


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def run_projection_path(workdir: Path, goal_id: str) -> Path:
    return paths.projections_dir(workdir, goal_id) / "run_projection.json"


def read_run_projection(workdir: Path, goal_id: str) -> dict[str, Any] | None:
    return read_json(run_projection_path(workdir, goal_id))


def read_task_structure(workdir: Path, goal_id: str) -> dict[str, Any] | None:
    return read_json(paths.projections_dir(workdir, goal_id) / "task_structure.json")


def read_obligation_ledger(workdir: Path, goal_id: str) -> dict[str, Any] | None:
    return read_json(paths.projections_dir(workdir, goal_id) / "obligation_ledger.json")


def events_db_path(workdir: Path, goal_id: str) -> Path:
    return paths.loop_goal_dir(workdir, goal_id) / "events.db"


def events_summary(workdir: Path, goal_id: str) -> dict[str, Any]:
    """Lightweight events.db health without full replay."""
    db = events_db_path(workdir, goal_id)
    out: dict[str, Any] = {
        "events_db": str(db),
        "present": db.is_file(),
        "event_count": 0,
        "hash_chain_ok": False,
        "last_sequence": -1,
        "last_type": None,
    }
    if not db.is_file():
        return out
    try:
        store = open_store(paths.loop_goal_dir(workdir, goal_id))
        events = store.read_all()
        out["event_count"] = len(events)
        if events:
            out["last_sequence"] = events[-1].sequence
            out["last_type"] = events[-1].type
        store.verify_hash_chain()
        out["hash_chain_ok"] = True
        store.close()
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    return out


def read_manifest_diagnostics(workdir: Path) -> dict[str, Any]:
    """Latest ``.local/runs/*/diagnostics.json`` (Manifest receipt sidecar)."""
    runs = workdir / ".local" / "runs"
    if not runs.is_dir():
        return {}
    candidates = sorted(runs.glob("*/diagnostics.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return {}
    try:
        raw = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def live_run_snapshot(workdir: Path, goal_id: str) -> dict[str, Any]:
    """Summary for benchmark drivers — projections first, events health."""
    rp = read_run_projection(workdir, goal_id) or {}
    quota = rp.get("quota") if isinstance(rp.get("quota"), dict) else {}
    ev = events_summary(workdir, goal_id)
    ts = read_task_structure(workdir, goal_id)
    root_status = None
    if isinstance(ts, dict) and isinstance(ts.get("root"), dict):
        root_status = ts["root"].get("status")
    return {
        "goal_id": goal_id,
        "run_status": rp.get("run_status"),
        "run_status_reason": rp.get("run_status_reason"),
        "last_sequence": rp.get("last_sequence"),
        "world_revision": rp.get("world_revision"),
        "quota": dict(quota),
        "events": ev,
        "task_root_status": root_status,
        "projection_path": str(run_projection_path(workdir, goal_id)),
        "manifest_diagnostics": read_manifest_diagnostics(workdir),
    }


def hydrate_quota_from_projection(
    quota: dict[str, Any],
    workdir: Path,
    goal_id: str,
) -> dict[str, Any]:
    """Overlay quota from run_projection (events.db SSOT)."""
    rp = read_run_projection(workdir, goal_id)
    if not rp:
        return quota
    q = rp.get("quota") if isinstance(rp.get("quota"), dict) else {}
    out = dict(quota)
    if q.get("cognitive_tokens") is not None:
        out["cognitive_tokens"] = int(q["cognitive_tokens"])
    if q.get("cognitive_tokens_max") is not None:
        out["cognitive_tokens_max"] = int(q["cognitive_tokens_max"])
    if q.get("repairs_used") is not None:
        out["repairs_used"] = int(q["repairs_used"])
    if q.get("repairs_max") is not None:
        out["repairs_max"] = int(q["repairs_max"])
    if q.get("usd_used") is not None:
        out["usd_used"] = float(q["usd_used"])
    return out


def read_last_tick_record(loop_dir: Path) -> dict[str, Any] | None:
    """Last line of ``ticks.jsonl`` (diagnostic; not SSOT)."""
    path = Path(loop_dir) / "ticks.jsonl"
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


def hydrate_runtime_signals(
    quota: dict[str, Any],
    loop_dir: Path,
    workdir: Path,
    goal_id: str,
) -> tuple[dict[str, Any], float | None, float | None]:
    """Overlay quota + focus/uncertainty from run_projection and ticks.jsonl."""
    out = hydrate_quota_from_projection(dict(quota), workdir, goal_id)
    focus: float | None = None
    uncertainty: float | None = None
    tick_rec = read_last_tick_record(loop_dir)
    if tick_rec:
        if tick_rec.get("focus_score") is not None:
            try:
                focus = float(tick_rec["focus_score"])
            except (TypeError, ValueError):
                pass
        if tick_rec.get("uncertainty") is not None:
            try:
                uncertainty = float(tick_rec["uncertainty"])
            except (TypeError, ValueError):
                pass
        if isinstance(tick_rec.get("quota"), dict):
            out.update(tick_rec["quota"])
    return out, focus, uncertainty
