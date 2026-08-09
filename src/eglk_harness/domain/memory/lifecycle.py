"""Σ/K memory isolation lifecycle: candidate→quarantined→verified→active→deprecated."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel.projections import MEMORY_RECORD_SCHEMA

LIFECYCLE = ("candidate", "quarantined", "verified", "active", "deprecated")


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_active_snapshot(workdir: Path) -> str:
    """Frozen digest of Σ.active at run start (no self-feedback)."""
    active_dir = paths.memory_lifecycle_dirs(workdir)["active"]
    active_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for p in sorted(active_dir.glob("*.json")):
        parts.append(p.name)
        parts.append(hashlib.sha256(p.read_bytes()).hexdigest())
    material = "|".join(parts) if parts else "empty-active"
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_active_records(workdir: Path) -> list[dict[str, Any]]:
    active_dir = paths.memory_lifecycle_dirs(workdir)["active"]
    out: list[dict[str, Any]] = []
    if not active_dir.is_dir():
        return out
    for p in sorted(active_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return out


def write_candidate(
    workdir: Path,
    *,
    kind: str,
    cond: str,
    wrong: str,
    correct: str,
    conf: float,
    namespace: str,
    origin_goal_id: str,
    origin_run_id: str,
    sensitive: bool = False,
) -> dict[str, Any]:
    """Write a candidate memory record — never readable by the producing run."""
    paths.ensure_memory_layout(workdir)
    rec = {
        "schema": MEMORY_RECORD_SCHEMA,
        "id": f"mem-{uuid.uuid4().hex[:12]}",
        "kind": kind if kind in {"sigma", "skill"} else "sigma",
        "cond": cond,
        "wrong": wrong,
        "correct": correct,
        "conf": max(0.0, min(1.0, float(conf))),
        "verifications": 0,
        "lifecycle_status": "candidate",
        "namespace": namespace,
        "ttl_at": None,
        "provenance": {
            "origin_goal_id": origin_goal_id,
            "origin_run_id": origin_run_id,
            "promoted_by_run_ids": [],
        },
        "last_used": 0,
        "sensitive": bool(sensitive),
    }
    dest = paths.memory_lifecycle_dirs(workdir)["candidate"] / f"{rec['id']}.json"
    dest.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec


def _move(rec_path: Path, dest_dir: Path, status: str, *, verifications: int | None = None) -> dict[str, Any]:
    data = json.loads(rec_path.read_text(encoding="utf-8"))
    data["lifecycle_status"] = status
    if verifications is not None:
        data["verifications"] = int(verifications)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / rec_path.name
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rec_path.unlink(missing_ok=True)
    return data


def promote(
    workdir: Path,
    record_id: str,
    *,
    to_status: str,
    by_run_id: str | None = None,
) -> dict[str, Any] | None:
    """Promote a record across lifecycle stages. Never promote into active with <2 verifications."""
    if to_status not in LIFECYCLE:
        raise ValueError(to_status)
    dirs = paths.memory_lifecycle_dirs(workdir)
    found: Path | None = None
    for d in dirs.values():
        cand = d / f"{record_id}.json"
        if cand.is_file():
            found = cand
            break
    if found is None:
        return None
    data = json.loads(found.read_text(encoding="utf-8"))
    ver = int(data.get("verifications") or 0)
    if to_status == "active" and ver < 2:
        raise ValueError("active requires verifications >= 2")
    if by_run_id:
        prov = dict(data.get("provenance") or {})
        promoted = list(prov.get("promoted_by_run_ids") or [])
        # Current run must not appear (no self-feedback)
        if by_run_id not in promoted:
            promoted.append(by_run_id)
        prov["promoted_by_run_ids"] = promoted
        data["provenance"] = prov
        found.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return _move(found, dirs[to_status], to_status, verifications=ver)


def quarantine_candidates(workdir: Path) -> int:
    """Move all candidate → quarantined at run end (Refiner batch)."""
    dirs = paths.memory_lifecycle_dirs(workdir)
    n = 0
    for p in list(dirs["candidate"].glob("*.json")):
        _move(p, dirs["quarantined"], "quarantined")
        n += 1
    return n


def bump_verification(workdir: Path, record_id: str) -> dict[str, Any] | None:
    dirs = paths.memory_lifecycle_dirs(workdir)
    for status, d in dirs.items():
        p = d / f"{record_id}.json"
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        data["verifications"] = int(data.get("verifications") or 0) + 1
        data["last_used"] = int(data.get("last_used") or 0) + 1
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return data
    return None
