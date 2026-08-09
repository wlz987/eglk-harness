"""Cross-run Σ lifecycle promotion — design ``context.md`` §3.2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.memory.lifecycle import expire_ttl_records

MIN_CONF_ACTIVE = 0.8
MIN_VERIFICATIONS_ACTIVE = 2
MIN_DISTINCT_GOALS_ACTIVE = 2


def _record_path(workdir: Path, record_id: str) -> Path | None:
    dirs = paths.memory_lifecycle_dirs(workdir)
    for d in dirs.values():
        p = d / f"{record_id}.json"
        if p.is_file():
            return p
    return None


def distinct_goal_ids(data: Mapping[str, Any]) -> set[str]:
    """Distinct goal ids that contributed verification (origin + cross-run reviews)."""
    out: set[str] = set()
    prov = data.get("provenance") if isinstance(data.get("provenance"), Mapping) else {}
    origin = str(prov.get("origin_goal_id") or data.get("namespace") or "").strip()
    if origin:
        out.add(origin)
    reviewed = prov.get("reviewed_goal_ids")
    if isinstance(reviewed, list):
        for gid in reviewed:
            s = str(gid).strip()
            if s:
                out.add(s)
    promoted = prov.get("promoted_by_run_ids")
    if isinstance(promoted, list):
        for rid in promoted:
            s = str(rid).strip()
            if s.startswith("run-") and "-seq" in s:
                mid = s[4:].rsplit("-seq", 1)[0]
                if mid:
                    out.add(mid)
    return out


def _mark_reviewed(workdir: Path, record_path: Path, goal_id: str) -> None:
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    prov = dict(data.get("provenance") or {})
    reviewed = [str(x) for x in (prov.get("reviewed_goal_ids") or []) if str(x).strip()]
    if goal_id not in reviewed:
        reviewed.append(goal_id)
    prov["reviewed_goal_ids"] = reviewed
    data["provenance"] = prov
    record_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def namespace_allows_promote(
    record: Mapping[str, Any],
    *,
    workdir_namespace: str | None = None,
) -> bool:
    """Block cross-namespace promotion when workdir namespace is set."""
    rec_ns = str(record.get("namespace") or "").strip()
    if not workdir_namespace:
        return True
    if not rec_ns:
        return True
    return rec_ns == workdir_namespace.strip()


def is_sensitive(record: Mapping[str, Any]) -> bool:
    return bool(record.get("sensitive"))


def quarantine_pending_candidates(workdir: Path, handler: Any | None = None) -> int:
    """Move ``candidate/`` → ``quarantined/`` (prior runs; not readable in-run)."""
    from eglk_harness.domain.memory.lifecycle import quarantine_candidates

    return quarantine_candidates(workdir, handler=handler)


def review_quarantined(
    workdir: Path,
    *,
    goal_id: str,
    origin_run_id: str,
    handler: Any | None = None,
) -> int:
    """Mechanical bump for quarantined records (tests / no adapter)."""
    from eglk_harness.domain.memory.lifecycle import bump_verification

    dirs = paths.memory_lifecycle_dirs(workdir)
    quarantined = dirs["quarantined"]
    if not quarantined.is_dir():
        return 0
    bumped = 0
    for p in sorted(quarantined.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if is_sensitive(data):
            continue
        prov = data.get("provenance") if isinstance(data.get("provenance"), Mapping) else {}
        origin_run = str(prov.get("origin_run_id") or "")
        if origin_run and origin_run == origin_run_id:
            continue
        rid = str(data.get("id") or p.stem)
        _mark_reviewed(workdir, p, goal_id)
        if bump_verification(workdir, rid) is None:
            continue
        bumped += 1
    return bumped


def promote_verified_eligible(
    workdir: Path,
    *,
    handler: Any | None = None,
    workdir_namespace: str | None = None,
) -> int:
    """``quarantined`` with ``verifications >= 2`` → ``verified``."""
    from eglk_harness.domain.memory.lifecycle import promote

    dirs = paths.memory_lifecycle_dirs(workdir)
    quarantined = dirs["quarantined"]
    if not quarantined.is_dir():
        return 0
    n = 0
    for p in sorted(quarantined.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or is_sensitive(data):
            continue
        if not namespace_allows_promote(data, workdir_namespace=workdir_namespace):
            continue
        ver = int(data.get("verifications") or 0)
        if ver < MIN_VERIFICATIONS_ACTIVE:
            continue
        rid = str(data.get("id") or p.stem)
        if promote(workdir, rid, to_status="verified", handler=handler, actor="refiner"):
            n += 1
    return n


def promote_active_eligible(
    workdir: Path,
    *,
    goal_id: str,
    origin_run_id: str,
    handler: Any | None = None,
    workdir_namespace: str | None = None,
) -> int:
    """``verified`` + conf + cross-goal → ``active`` (skill_lib mechanical approval)."""
    from eglk_harness.domain.memory.lifecycle import promote

    dirs = paths.memory_lifecycle_dirs(workdir)
    verified = dirs["verified"]
    if not verified.is_dir():
        return 0
    n = 0
    for p in sorted(verified.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or is_sensitive(data):
            continue
        if not namespace_allows_promote(data, workdir_namespace=workdir_namespace):
            continue
        conf = float(data.get("conf") or 0)
        if conf < MIN_CONF_ACTIVE:
            continue
        ver = int(data.get("verifications") or 0)
        if ver < MIN_VERIFICATIONS_ACTIVE:
            continue
        goals = distinct_goal_ids(data)
        if len(goals) < MIN_DISTINCT_GOALS_ACTIVE:
            continue
        prov = data.get("provenance") if isinstance(data.get("provenance"), Mapping) else {}
        origin_run = str(prov.get("origin_run_id") or "")
        if origin_run and origin_run == origin_run_id:
            continue
        rid = str(data.get("id") or p.stem)
        try:
            if promote(
                workdir,
                rid,
                to_status="active",
                by_run_id=origin_run_id,
                handler=handler,
                actor="refiner",
            ):
                n += 1
        except ValueError:
            continue
    return n


def run_cross_run_promotion(
    workdir: Path,
    *,
    goal_id: str,
    origin_run_id: str,
    handler: Any | None = None,
    workdir_namespace: str | None = None,
) -> dict[str, int]:
    """Sync cross-run batch (mechanical review bump)."""
    ns = workdir_namespace or goal_id
    expired = expire_ttl_records(workdir, handler=handler)
    quarantined = quarantine_pending_candidates(workdir, handler=handler)
    bumped = review_quarantined(
        workdir, goal_id=goal_id, origin_run_id=origin_run_id, handler=handler
    )
    to_verified = promote_verified_eligible(
        workdir, handler=handler, workdir_namespace=ns
    )
    to_active = promote_active_eligible(
        workdir,
        goal_id=goal_id,
        origin_run_id=origin_run_id,
        handler=handler,
        workdir_namespace=ns,
    )
    return {
        "ttl_expired": expired,
        "quarantined": quarantined,
        "verification_bumps": bumped,
        "promoted_verified": to_verified,
        "promoted_active": to_active,
    }


async def run_cross_run_promotion_async(
    workdir: Path,
    adapter: AgentAdapter | None,
    *,
    goal_id: str,
    origin_run_id: str,
    handler: Any | None = None,
    workdir_namespace: str | None = None,
) -> dict[str, Any]:
    """TTL expire + quarantine + LLM quarantine review + verified/active promotion."""
    from eglk_harness.domain.memory.refiner_quarantine import llm_review_quarantined

    expired = expire_ttl_records(workdir, handler=handler)
    quarantined = quarantine_pending_candidates(workdir, handler=handler)
    llm_stats = await llm_review_quarantined(
        adapter,
        workdir,
        goal_id=goal_id,
        origin_run_id=origin_run_id,
        handler=handler,
    )
    ns = workdir_namespace or goal_id
    to_verified = promote_verified_eligible(
        workdir, handler=handler, workdir_namespace=ns
    )
    to_active = promote_active_eligible(
        workdir,
        goal_id=goal_id,
        origin_run_id=origin_run_id,
        handler=handler,
        workdir_namespace=ns,
    )
    return {
        "ttl_expired": expired,
        "quarantined": quarantined,
        **llm_stats,
        "promoted_verified": to_verified,
        "promoted_active": to_active,
    }
