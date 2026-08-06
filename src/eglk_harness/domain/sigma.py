"""Σ (sigma) store: authority under memory/; refined/ is tick staging only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eglk_harness.domain import paths


def active_path(workdir: Path) -> Path:
    return paths.memory_sigma_dir(workdir) / "active.json"


def archived_path(workdir: Path) -> Path:
    return paths.memory_sigma_dir(workdir) / "archived.json"


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def save_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_active(workdir: Path) -> list[dict[str, Any]]:
    return load_json_list(active_path(workdir))


def save_active(workdir: Path, items: list[dict[str, Any]]) -> None:
    save_json_list(active_path(workdir), items)


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


def merge_refined_into_active(workdir: Path, loop_dir: Path) -> int:
    """Phase 3: atomically fold refined/ into memory sigma active; clear staging.

    Returns number of items merged. Must run *after* Gate so same-tick Gate
    never sees these Σ updates. Dedupes by ``id``; overflows to archived when
    active exceeds ``SIGMA_ACTIVE_MAX``.
    """
    from eglk_harness.domain import projections as P

    refined = list_refined(loop_dir)
    if not refined:
        return 0
    active = load_active(workdir)
    by_id = {str(it.get("id")): it for it in active if it.get("id")}
    merged = 0
    for path in refined:
        item = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(item, dict):
            iid = str(item.get("id") or f"anon-{path.stem}")
            item = dict(item)
            item["id"] = iid
            by_id[iid] = item
            merged += 1
        path.unlink(missing_ok=True)
    active = list(by_id.values())
    archived = load_json_list(archived_path(workdir))
    if len(active) > P.SIGMA_ACTIVE_MAX:
        overflow = active[: -P.SIGMA_ACTIVE_MAX]
        keep = active[-P.SIGMA_ACTIVE_MAX :]
        for item in overflow:
            archived.append({**item, "status": "frozen"})
        active = keep
        save_json_list(archived_path(workdir), archived)
    save_active(workdir, active)
    return merged
