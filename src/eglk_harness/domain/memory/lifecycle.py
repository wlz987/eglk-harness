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


def _is_sensitive_record(data: Mapping[str, Any]) -> bool:
    return bool(data.get("sensitive"))


def digest_active_snapshot(workdir: Path) -> str:
    """Frozen digest of Σ.active at run start (no self-feedback; excludes sensitive)."""
    active_dir = paths.memory_lifecycle_dirs(workdir)["active"]
    active_dir.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for p in sorted(active_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and _is_sensitive_record(data):
            continue
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
            if isinstance(data, dict) and not _is_sensitive_record(data):
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
    handler: Any | None = None,
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
    if handler is not None and hasattr(handler, "memory_candidate_written"):
        handler.memory_candidate_written(rec, actor="maker")
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


def _parse_ttl_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def expire_ttl_records(workdir: Path, handler: Any | None = None) -> int:
    """Move records past ``ttl_at`` to ``deprecated`` (mechanical)."""
    dirs = paths.memory_lifecycle_dirs(workdir)
    now = datetime.now(timezone.utc)
    n = 0
    for status in ("candidate", "quarantined", "verified", "active"):
        stage_dir = dirs[status]
        if not stage_dir.is_dir():
            continue
        for p in list(stage_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            ttl = _parse_ttl_at(data.get("ttl_at"))
            if ttl is None or ttl > now:
                continue
            rid = str(data.get("id") or p.stem)
            from_status = str(data.get("lifecycle_status") or status)
            _move(p, dirs["deprecated"], "deprecated")
            if handler is not None and hasattr(handler, "memory_deprecated"):
                handler.memory_deprecated(
                    record_id=rid,
                    from_status=from_status,
                    reason="ttl_expired",
                    actor="refiner",
                )
            n += 1
    return n


def deprecate_record(
    workdir: Path,
    record_id: str,
    *,
    reason: str = "refiner_reject",
    handler: Any | None = None,
    actor: str = "refiner",
) -> dict[str, Any] | None:
    """Move any lifecycle record to ``deprecated``."""
    dirs = paths.memory_lifecycle_dirs(workdir)
    found: Path | None = None
    from_status = ""
    for status, d in dirs.items():
        if status == "deprecated":
            continue
        p = d / f"{record_id}.json"
        if p.is_file():
            found = p
            from_status = status
            break
    if found is None:
        return None
    result = _move(found, dirs["deprecated"], "deprecated")
    if handler is not None and hasattr(handler, "memory_deprecated"):
        handler.memory_deprecated(
            record_id=record_id,
            from_status=from_status or str(result.get("lifecycle_status") or ""),
            reason=reason,
            actor=actor,
        )
    return result


def promote(
    workdir: Path,
    record_id: str,
    *,
    to_status: str,
    by_run_id: str | None = None,
    handler: Any | None = None,
    actor: str = "refiner",
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
    from_status = str(data.get("lifecycle_status") or "")
    ver = int(data.get("verifications") or 0)
    if to_status == "active" and ver < 2:
        raise ValueError("active requires verifications >= 2")
    if to_status == "active" and _is_sensitive_record(data):
        raise ValueError("sensitive records cannot enter active")
    if by_run_id:
        prov = dict(data.get("provenance") or {})
        promoted = list(prov.get("promoted_by_run_ids") or [])
        # Current run must not appear (no self-feedback)
        if by_run_id not in promoted:
            promoted.append(by_run_id)
        prov["promoted_by_run_ids"] = promoted
        data["provenance"] = prov
        found.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result = _move(found, dirs[to_status], to_status, verifications=ver)
    if handler is not None and hasattr(handler, "memory_promoted"):
        handler.memory_promoted(
            record_id=record_id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
        )
    return result


def quarantine_candidates(workdir: Path, handler: Any | None = None) -> int:
    """Move all candidate → quarantined at run end (Refiner batch)."""
    dirs = paths.memory_lifecycle_dirs(workdir)
    n = 0
    for p in list(dirs["candidate"].glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        rid = str(data.get("id") or p.stem)
        _move(p, dirs["quarantined"], "quarantined")
        if handler is not None and hasattr(handler, "memory_promoted"):
            handler.memory_promoted(
                record_id=rid,
                from_status="candidate",
                to_status="quarantined",
                actor="refiner",
            )
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
