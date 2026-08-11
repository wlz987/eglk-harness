"""Closure Gate evidence — re-bind satisfied obligations at current world_revision.

Semantic ``watch_set`` entries (``task_type:RETRIEVE``) are not disk paths.
Closure reuses the latest leaf ``EvidenceRecorded`` attestations and path-like
watch entries only (design semantic_core.md §8).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel.attestation import attestation_valid_for_obligation
from eglk_harness.domain.kernel.reducer import ObligationState

_SEMANTIC_WATCH_RE = re.compile(r"^[A-Za-z_][\w.-]*:")


def is_path_like_watch_entry(entry: str) -> bool:
    """True when a watch_set line is a workdir-relative path, not a semantic tag."""
    s = str(entry or "").strip().lstrip("/").replace("\\", "/")
    if not s or ".." in Path(s).parts:
        return False
    if s.startswith("workdir/"):
        s = s[len("workdir/") :]
    if _SEMANTIC_WATCH_RE.match(s):
        return False
    if "/" in s:
        return True
    suffix = Path(s).suffix.lower()
    return suffix in {".json", ".har", ".txt", ".md", ".yaml", ".yml", ".png", ".jpg", ".jpeg"}


def path_like_watch_entries(watch_set: Sequence[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in watch_set or []:
        s = str(raw).strip().lstrip("/").replace("\\", "/")
        if s.startswith("workdir/"):
            s = s[len("workdir/") :]
        if not is_path_like_watch_entry(s):
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:" + h.hexdigest()


def file_attestation(
    workdir: Path,
    rel: str,
    *,
    world_revision: int,
    method: str,
    observer: str,
    watch_set: Sequence[str] | None = None,
) -> dict[str, Any] | None:
    rel_s = str(rel).strip().lstrip("/").replace("\\", "/")
    if rel_s.startswith("workdir/"):
        rel_s = rel_s[len("workdir/") :]
    if not rel_s:
        return None
    path = workdir / rel_s
    digest = _sha256_file(path) if path.is_file() else "missing"
    return {
        "method": method,
        "world_revision": int(world_revision),
        "digest": digest,
        "observer": observer,
        "raw_ref": rel_s,
        "watch_set": list(watch_set or [rel_s]),
    }


def rebind_attestations(
    workdir: Path,
    attestations: Sequence[Mapping[str, Any]],
    *,
    world_revision: int,
    verification_type: str,
    observer: str = "closure-rebind",
) -> list[dict[str, Any]]:
    """Copy prior attestations; refresh digests for on-disk ``raw_ref`` at ``world_revision``."""
    out: list[dict[str, Any]] = []
    for raw in attestations:
        if not isinstance(raw, Mapping):
            continue
        rel = str(raw.get("raw_ref") or "").strip().lstrip("/").replace("\\", "/")
        if rel.startswith("workdir/"):
            rel = rel[len("workdir/") :]
        method = str(raw.get("method") or verification_type or "custom_attestation")
        watch = raw.get("watch_set")
        watch_list = [str(x) for x in watch] if isinstance(watch, (list, tuple)) else ([rel] if rel else [])
        if rel:
            att = file_attestation(
                workdir,
                rel,
                world_revision=world_revision,
                method=method,
                observer=str(raw.get("observer") or observer),
                watch_set=watch_list,
            )
            if att is None:
                continue
            # Keep scout / non-file refs only when digest is not missing
            if att["digest"] == "missing" and not rel.endswith(".json"):
                att = dict(att)
                att["digest"] = str(raw.get("digest") or "missing")
        else:
            att = {
                "method": method,
                "world_revision": int(world_revision),
                "digest": str(raw.get("digest") or "missing"),
                "observer": str(raw.get("observer") or observer),
                "raw_ref": rel or str(raw.get("raw_ref") or "unknown"),
                "watch_set": watch_list,
            }
        if attestation_valid_for_obligation(
            att,
            verification_type=verification_type,
            expected_world_revision=world_revision,
        ):
            out.append(att)
    return out


def find_latest_satisfied_verdict(
    events: Sequence[Any],
    obligation_id: str,
) -> dict[str, Any] | None:
    """Latest ``EvidenceRecorded`` verdict with ``status=satisfied`` for ``obligation_id``."""
    oid = str(obligation_id)
    for ev in reversed(events):
        if getattr(ev, "type", None) != "EvidenceRecorded":
            continue
        payload = getattr(ev, "payload", None) or {}
        evidence = payload.get("evidence") if isinstance(payload, Mapping) else None
        if not isinstance(evidence, dict):
            continue
        for verdict in evidence.get("verdicts") or []:
            if not isinstance(verdict, dict):
                continue
            if str(verdict.get("obligation_id")) != oid:
                continue
            if str(verdict.get("status") or "") == "satisfied":
                return dict(verdict)
    return None


def build_closure_verdict(
    workdir: Path,
    obligation: ObligationState,
    *,
    world_revision: int,
    events: Sequence[Any],
    observer: str = "closure-checker",
) -> dict[str, Any]:
    """Build one closure verdict for a root obligation (truth-blind; no Oracle)."""
    oid = obligation.id
    vt = str(obligation.verification_type or "custom_attestation")

    if obligation.status != "satisfied":
        return {
            "obligation_id": oid,
            "status": "unsatisfied",
            "attestations": [],
            "gaps": ["closure_incomplete"],
            "defect_suspected": False,
        }

    attestations: list[dict[str, Any]] = []

    prior = find_latest_satisfied_verdict(events, oid)
    if prior is not None:
        attestations = rebind_attestations(
            workdir,
            prior.get("attestations") or [],
            world_revision=world_revision,
            verification_type=vt,
            observer=observer,
        )

    for rel in path_like_watch_entries(obligation.watch_set):
        if any(a.get("raw_ref") == rel for a in attestations):
            continue
        att = file_attestation(
            workdir,
            rel,
            world_revision=world_revision,
            method=vt if vt == "file_exists" else "file_exists",
            observer=observer,
            watch_set=list(obligation.watch_set or []),
        )
        if att and attestation_valid_for_obligation(
            att, verification_type=vt, expected_world_revision=world_revision
        ):
            attestations.append(att)

    if attestations:
        return {
            "obligation_id": oid,
            "status": "satisfied",
            "attestations": attestations,
            "gaps": [],
            "defect_suspected": False,
        }

    return {
        "obligation_id": oid,
        "status": "unsatisfied",
        "attestations": [],
        "gaps": ["closure:missing_rebind_attestation"],
        "defect_suspected": False,
    }
