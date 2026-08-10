"""Σ (sigma) store: lifecycle ``active/`` is SSOT; loop ``refined/`` is tick staging only."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eglk_harness.domain.kernel import paths


def _legacy_active_json_path(workdir: Path) -> Path:
    return paths.memory_sigma_dir(workdir) / "active.json"


def _legacy_archived_json_path(workdir: Path) -> Path:
    return paths.memory_sigma_dir(workdir) / "archived.json"


def _active_dir(workdir: Path) -> Path:
    return paths.memory_lifecycle_dirs(workdir)["active"]


def _deprecated_dir(workdir: Path) -> Path:
    return paths.memory_lifecycle_dirs(workdir)["deprecated"]


def _safe_record_name(record_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", record_id)[:120]
    return safe or "record"


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _migrate_legacy_active_json(workdir: Path) -> None:
    """One-time import ``active.json`` → ``memory/sigma/active/*.json``."""
    legacy = _legacy_active_json_path(workdir)
    if not legacy.is_file():
        return
    active_dir = _active_dir(workdir)
    if any(active_dir.glob("*.json")):
        return
    for item in load_json_list(legacy):
        rid = str(item.get("id") or f"legacy-{hash(json.dumps(item)) & 0xfffffff}")
        item = dict(item)
        item["id"] = rid
        if not item.get("lifecycle_status"):
            item["lifecycle_status"] = "active"
        path = active_dir / f"{_safe_record_name(rid)}.json"
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        legacy.unlink(missing_ok=True)
    except OSError:
        pass


def _migrate_legacy_archived_json(workdir: Path) -> None:
    legacy = _legacy_archived_json_path(workdir)
    if not legacy.is_file():
        return
    dep = _deprecated_dir(workdir)
    if any(dep.glob("*.json")):
        return
    for item in load_json_list(legacy):
        rid = str(item.get("id") or f"arch-{hash(json.dumps(item)) & 0xfffffff}")
        item = dict(item)
        item["id"] = rid
        item["lifecycle_status"] = "deprecated"
        path = dep / f"{_safe_record_name(rid)}.json"
        path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        legacy.unlink(missing_ok=True)
    except OSError:
        pass


def load_active(workdir: Path) -> list[dict[str, Any]]:
    """Σ active records from lifecycle ``active/`` (not ``active.json``)."""
    paths.ensure_memory_layout(workdir)
    _migrate_legacy_active_json(workdir)
    _migrate_legacy_archived_json(workdir)
    active_dir = _active_dir(workdir)
    active_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for p in sorted(active_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and not data.get("sensitive"):
            out.append(data)
    return out


def save_active_record(workdir: Path, record: dict[str, Any]) -> Path:
    """Upsert one active Σ record under lifecycle ``active/``."""
    rid = str(record.get("id") or "")
    if not rid:
        raise ValueError("active record requires id")
    active_dir = _active_dir(workdir)
    active_dir.mkdir(parents=True, exist_ok=True)
    doc = dict(record)
    doc.setdefault("lifecycle_status", "active")
    path = active_dir / f"{_safe_record_name(rid)}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def save_active(workdir: Path, items: list[dict[str, Any]]) -> None:
    """Replace lifecycle ``active/`` contents with ``items`` (by record id)."""
    active_dir = _active_dir(workdir)
    active_dir.mkdir(parents=True, exist_ok=True)
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "")
        if not rid:
            continue
        by_id[rid] = dict(item)
    for p in active_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            rid = str(data.get("id") or p.stem)
        except (OSError, json.JSONDecodeError):
            rid = p.stem
        if rid not in by_id:
            p.unlink(missing_ok=True)
    for rid, item in by_id.items():
        save_active_record(workdir, item)


# Back-compat aliases (deprecated paths)
def active_path(workdir: Path) -> Path:
    return _active_dir(workdir)


def archived_path(workdir: Path) -> Path:
    return _deprecated_dir(workdir)


def refined_dir(loop_dir: Path) -> Path:
    d = loop_dir / "sigma" / "refined"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_refined(loop_dir: Path, tick: int, item: dict[str, Any]) -> Path:
    path = refined_dir(loop_dir) / f"{tick:03d}.json"
    path.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def list_refined(loop_dir: Path) -> list[Path]:
    d = loop_dir / "sigma" / "refined"
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.is_file())


def enforce_staging_cap(loop_dir: Path, *, max_items: int | None = None) -> int:
    """Mechanically archive oldest ``sigma/refined/`` entries when over ``SIGMA_STAGING_MAX``."""
    from eglk_harness.domain.kernel.projections import effective_sigma_staging_max

    cap = int(max_items or effective_sigma_staging_max())
    paths_list = list_refined(loop_dir)
    if len(paths_list) <= cap:
        return 0
    overflow = paths_list[: len(paths_list) - cap]
    merged_texts: list[str] = []
    merged_ids: list[str] = []
    for path in overflow:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            continue
        if isinstance(item, dict):
            merged_ids.append(str(item.get("id") or path.stem))
            merged_texts.append(str(item.get("text") or item.get("cond") or item.get("kind") or ""))
        path.unlink(missing_ok=True)
    archive_path = refined_dir(loop_dir) / f"archive_{overflow[0].stem}_{overflow[-1].stem}.json"
    archive = {
        "id": f"sigma-archive-{overflow[0].stem}-{overflow[-1].stem}",
        "kind": "archive",
        "text": " | ".join(t for t in merged_texts if t)[:2000],
        "merged_from": merged_ids,
        "staged": "mechanical_cap",
        "conf": 0.4,
    }
    archive_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(overflow)


def merge_refined_into_active(workdir: Path, loop_dir: Path) -> int:
    """Legacy shim — run-end batch writes ``candidate`` only."""
    return flush_refined_to_candidates(
        workdir,
        loop_dir,
        goal_id=loop_dir.name,
        origin_run_id=f"run-{loop_dir.name}-legacy",
        handler=None,
    )


def flush_refined_to_candidates(
    workdir: Path,
    loop_dir: Path,
    *,
    goal_id: str,
    origin_run_id: str,
    handler: Any | None = None,
) -> int:
    """Move ``sigma/refined/`` into lifecycle ``candidate`` (never ``active`` in same run)."""
    from eglk_harness.domain.memory.lifecycle import write_candidate

    refined = list_refined(loop_dir)
    if not refined:
        return 0
    flushed = 0
    for path in refined:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            continue
        if not isinstance(item, dict):
            path.unlink(missing_ok=True)
            continue
        text = str(item.get("text") or item.get("correct") or item.get("kind") or "")
        cond = str(item.get("cond") or item.get("reason") or item.get("kind") or "lesson")
        wrong = str(item.get("wrong") or item.get("gaps") or "")
        conf = float(item.get("conf") or 0.5)
        write_candidate(
            workdir,
            kind="sigma",
            cond=cond,
            wrong=wrong if wrong else text[:200],
            correct=text,
            conf=conf,
            namespace=goal_id,
            origin_goal_id=goal_id,
            origin_run_id=origin_run_id,
            handler=handler,
        )
        flushed += 1
        path.unlink(missing_ok=True)
    return flushed
