"""Eval Run Manifest under ``.local/runs/<run_id>/`` (no WA-Hard dependency)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from eglk_harness import __version__
from eglk_harness.domain import paths
from eglk_harness.domain import projections as P


def local_runs_root(workdir: Path) -> Path:
    return workdir / ".local" / "runs"


def new_run_id(prefix: str = "eglk") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{prefix}"


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml_dump(data: Mapping[str, Any], *, indent: int = 0) -> str:
    """Minimal YAML emitter for Manifest (stdlib only)."""
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
                    # inline nested poorly — use json for complex list items
                    lines.append(f"{pad}  {json.dumps(item, ensure_ascii=False)}")
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
    decision = decision or {}
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "schema_version": P.GOAL_SCHEMA_VERSION,
        "architecture_version": __version__,
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "initiator": "eglk-auto",
        "model": {
            "id": model or "",
            "api_base": "",
            "decoding": {"temperature": 0.0},
        },
        "pack": "local",
        "variant": "full",
        "kernel_commit": kernel_commit or "",
        "adapter": agent,
        "mcp_config_sha256": _sha256_file(mcp_config),
        "sandbox_mode": "strict",
        "swarm_soft": swarm,
        "budget": {
            "cognitive_tokens_max": P.COGNITIVE_TOKENS_MAX,
            "repairs_max": P.REPAIRS_MAX,
            # soft tick cap may be recorded later; never replaces cognitive/repairs
            "max_ticks_soft": 0,
        },
        "goal_id": goal_id,
        "workdir": str(workdir.resolve()),
        "loop_uri": f"local:{paths.loop_goal_dir(workdir, goal_id)}",
        "results_uri": f"local:.local/runs/{run_id}",
        "last_decision": {
            "decision": decision.get("decision"),
            "reason": decision.get("reason"),
        },
    }
    if extra:
        manifest.update(dict(extra))
    return manifest


def write_manifest(workdir: Path, manifest: Mapping[str, Any]) -> Path:
    """Write ``.local/runs/<run_id>/manifest.yaml`` (+ json twin)."""
    run_id = str(manifest.get("run_id") or new_run_id())
    root = local_runs_root(workdir) / run_id
    root.mkdir(parents=True, exist_ok=True)
    yaml_path = root / "manifest.yaml"
    json_path = root / "manifest.json"
    yaml_path.write_text(_yaml_dump(manifest) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(dict(manifest), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # empty metrics placeholder for eval connectors
    metrics = root / "metrics.csv"
    if not metrics.is_file():
        metrics.write_text("metric,value\n", encoding="utf-8")
    return yaml_path
