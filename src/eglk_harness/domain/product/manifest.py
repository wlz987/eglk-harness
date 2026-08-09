"""RunManifest export — schema ``eglk.run_manifest`` (eval-facing receipt)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from eglk_harness import __version__
from eglk_harness.domain.kernel import paths
from eglk_harness.domain.kernel import projections as P
from eglk_harness.domain.kernel.schema_validate import validate_document
from eglk_harness.domain.memory.lifecycle import digest_active_snapshot


def local_runs_root(workdir: Path) -> Path:
    return workdir / ".local" / "runs"


def new_run_id(prefix: str = "eglk") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{prefix}"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _sha256_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return _sha256_text("")
    return _sha256_bytes(path.read_bytes())


def _sha256_path_tree(root: Path) -> str:
    if not root.is_dir():
        return _sha256_text("")
    parts: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(root))
            parts.append(rel)
            parts.append(hashlib.sha256(p.read_bytes()).hexdigest())
    return _sha256_text("|".join(parts) if parts else "empty")


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _yaml_dump(data: Mapping[str, Any], *, indent: int = 0) -> str:
    lines: list[str] = []
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, Mapping):
            lines.append(f"{pad}{key}:")
            lines.append(_yaml_dump(value, indent=indent + 1))
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, Mapping):
                    lines.append(f"{pad}-")
                    lines.append(_yaml_dump(item, indent=indent + 1))
                else:
                    lines.append(f"{pad}- {json.dumps(item, ensure_ascii=False)}")
        elif value is None:
            lines.append(f"{pad}{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{pad}{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{pad}{key}: {value}")
        else:
            lines.append(f"{pad}{key}: {json.dumps(str(value), ensure_ascii=False)}")
    return "\n".join(lines)


def build_digests(
    *,
    workdir: Path,
    agent: str,
    model: str | None,
    mcp_config: Path | None,
    capability_manifest: Path | None,
) -> dict[str, str]:
    goal = paths.goal_path(workdir)
    schema_dir = Path(__file__).resolve().parent.parent / "schemas"
    skills_dir = Path(__file__).resolve().parent.parent / "memory" / "skills"
    return {
        "goal": _sha256_file(goal),
        "schema_family": _sha256_path_tree(schema_dir),
        "model": _sha256_text(model or ""),
        "prompt": _sha256_path_tree(skills_dir),
        "tool": _sha256_file(mcp_config) if mcp_config else _sha256_text("tools-default"),
        "adapter": _sha256_text(agent),
        "capability_manifest": _sha256_file(capability_manifest),
        "memory": digest_active_snapshot(workdir),
        "environment": _sha256_text(f"workdir:{workdir.resolve()}"),
    }


def build_quota_snapshot(
    *,
    cognitive_tokens: int = 0,
    cognitive_tokens_max: int | None = None,
    cognitive_tokens_by_role: Mapping[str, int] | None = None,
    repairs_used: int = 0,
    repairs_max: int | None = None,
    usd_used: float = 0.0,
) -> dict[str, Any]:
    return {
        "schema": P.QUOTA_SCHEMA,
        "cognitive_tokens": int(cognitive_tokens),
        "cognitive_tokens_max": int(
            cognitive_tokens_max if cognitive_tokens_max is not None else P.effective_cognitive_tokens_max()
        ),
        "cognitive_tokens_by_role": {
            str(k): int(v) for k, v in dict(cognitive_tokens_by_role or {}).items()
        },
        "repairs_used": int(repairs_used),
        "repairs_max": int(repairs_max if repairs_max is not None else P.effective_repairs_max()),
        "usd_used": float(usd_used),
    }


def build_run_manifest(
    *,
    run_id: str,
    workdir: Path,
    goal_id: str,
    run_status: str,
    agent: str,
    model: str | None = None,
    mcp_config: Path | None = None,
    run_status_reason: str | None = None,
    quota: Mapping[str, Any] | None = None,
    event_log_hash: str | None = None,
    created_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    """Build a schema-valid ``eglk.run_manifest`` document."""
    workdir = Path(workdir).resolve()
    status = run_status if run_status in {"succeeded", "aborted", "invalid", "faulted"} else "faulted"
    cap = paths.capability_manifest_path(workdir)
    tip = event_log_hash or _sha256_text("empty-log")
    if tip and not tip.startswith("sha256:"):
        tip = "sha256:" + tip if len(tip) == 64 else _sha256_text(tip)

    q_in = dict(quota or {})
    quota_doc = build_quota_snapshot(
        cognitive_tokens=int(q_in.get("cognitive_tokens") or 0),
        cognitive_tokens_max=q_in.get("cognitive_tokens_max"),
        cognitive_tokens_by_role=q_in.get("cognitive_tokens_by_role")
        if isinstance(q_in.get("cognitive_tokens_by_role"), Mapping)
        else {},
        repairs_used=int(q_in.get("repairs_used") or 0),
        repairs_max=q_in.get("repairs_max"),
        usd_used=float(q_in.get("usd_used") or 0.0),
    )

    now = _utcnow()
    doc = {
        "schema": P.RUN_MANIFEST_SCHEMA,
        "run_id": run_id,
        "goal_id": goal_id,
        "run_status": status,
        "run_status_reason": run_status_reason,
        "digests": build_digests(
            workdir=workdir,
            agent=agent,
            model=model,
            mcp_config=mcp_config,
            capability_manifest=cap if cap.is_file() else None,
        ),
        "quota": quota_doc,
        "created_at": created_at or now,
        "finished_at": finished_at or now,
        "event_log_hash": tip,
    }
    return doc


def build_manifest(
    *,
    run_id: str,
    workdir: Path,
    goal_id: str,
    agent: str,
    model: str | None = None,
    mcp_config: Path | None = None,
    swarm: str | None = None,
    decision: Mapping[str, Any] | None = None,
    kernel_commit: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper — prefer ``build_run_manifest`` for receipts.

    Returns the schema-valid RunManifest, optionally merging non-schema diagnostics
    into a sibling ``diagnostics`` file via ``write_manifest``.
    """
    extra = dict(extra or {})
    decision = decision or {}
    run_status = str(extra.get("run_status") or "faulted")
    if run_status not in {"succeeded", "aborted", "invalid", "faulted"}:
        # Soft max_ticks halt while still running → treat receipt as aborted? No —
        # schema only allows terminal statuses. Map soft-running to faulted only if
        # forced; prefer aborted with reason when stop was resource-like.
        stop = str(extra.get("stop_reason") or "")
        if stop.startswith("abort"):
            run_status = "aborted"
        elif stop in {"root_admitted"} or decision.get("decision") == "admit":
            run_status = "succeeded"
        elif stop.startswith("terminal:"):
            run_status = stop.split(":", 1)[-1]
            if run_status not in {"succeeded", "aborted", "invalid", "faulted"}:
                run_status = "faulted"
        else:
            # Non-terminal soft stop: still emit a receipt marked aborted with reason
            # so eval can read it; soft max_ticks is not Gate abort authority.
            run_status = "aborted"
            extra.setdefault("run_status_reason", f"soft_stop:{stop or 'incomplete'}")

    quota = extra.get("quota") if isinstance(extra.get("quota"), Mapping) else None
    doc = build_run_manifest(
        run_id=run_id,
        workdir=workdir,
        goal_id=goal_id,
        run_status=run_status,
        agent=agent,
        model=model,
        mcp_config=mcp_config,
        run_status_reason=extra.get("run_status_reason")
        or (decision.get("reason") if isinstance(decision, Mapping) else None),
        quota=quota,
        event_log_hash=extra.get("event_log_hash") if isinstance(extra.get("event_log_hash"), str) else None,
    )
    # Attach opaque diagnostics for humans (stripped before schema validate on write)
    diagnostics = {
        "architecture_version": __version__,
        "schema_family": "eglk",
        "adapter": agent,
        "swarm_soft": swarm,
        "kernel_commit": kernel_commit or "",
        "last_decision": {
            "decision": decision.get("decision") if isinstance(decision, Mapping) else None,
            "reason": decision.get("reason") if isinstance(decision, Mapping) else None,
        },
        "workdir": str(Path(workdir).resolve()),
        "loop_uri": f"local:{paths.loop_goal_dir(workdir, goal_id)}",
        "results_uri": f"local:.local/runs/{run_id}",
    }
    for k in (
        "engine",
        "ticks_run",
        "max_ticks_soft",
        "stop_reason",
        "budget_note",
        "advisor",
    ):
        if k in extra:
            diagnostics[k] = extra[k]
    doc["_diagnostics"] = diagnostics
    return doc


def write_manifest(workdir: Path, manifest: Mapping[str, Any]) -> Path:
    """Write schema-valid ``manifest.json`` (+ yaml twin) and diagnostics sidecar."""
    run_id = str(manifest.get("run_id") or new_run_id())
    root = local_runs_root(workdir) / run_id
    root.mkdir(parents=True, exist_ok=True)

    body = {k: v for k, v in dict(manifest).items() if not str(k).startswith("_")}
    diagnostics = manifest.get("_diagnostics") if isinstance(manifest.get("_diagnostics"), Mapping) else {}

    errs = validate_document("run_manifest", body)
    if errs:
        # Best-effort repair: ensure required digests/quota shapes
        raise ValueError(f"RunManifest schema invalid: {errs[:5]}")

    json_path = root / "manifest.json"
    yaml_path = root / "manifest.yaml"
    json_path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    yaml_path.write_text(_yaml_dump(body) + "\n", encoding="utf-8")
    if diagnostics:
        (root / "diagnostics.json").write_text(
            json.dumps(dict(diagnostics), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    metrics = root / "metrics.csv"
    if not metrics.is_file():
        metrics.write_text("metric,value\n", encoding="utf-8")
    return yaml_path
