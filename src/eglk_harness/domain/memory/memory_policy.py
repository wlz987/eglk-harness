"""Eval / campaign memory policy — frozen active snapshots (``context.md`` §3.5)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

_FROZEN_DIGEST: str | None = None


def eval_freeze_memory(env: Mapping[str, str] | None = None) -> bool:
    env = env or os.environ
    raw = (env.get("EGLK_EVAL_FREEZE_MEMORY") or env.get("EGLK_MEMORY_FROZEN") or "").strip()
    return raw.lower() in {"1", "true", "yes", "on"}


def memory_sharing_label(env: Mapping[str, str] | None = None) -> str:
    if eval_freeze_memory(env):
        return "frozen_active"
    return "workdir_default"


def set_frozen_digest(digest: str) -> None:
    global _FROZEN_DIGEST
    _FROZEN_DIGEST = digest if digest.startswith("sha256:") else f"sha256:{digest}"


def get_frozen_digest() -> str | None:
    return _FROZEN_DIGEST


def bootstrap_frozen_digest(workdir: Path, env: Mapping[str, str] | None = None) -> str | None:
    """On first run in eval-freeze mode, pin active digest for the process."""
    if not eval_freeze_memory(env):
        return None
    if _FROZEN_DIGEST:
        return _FROZEN_DIGEST
    from eglk_harness.domain.memory.lifecycle import digest_active_snapshot

    digest = digest_active_snapshot(workdir)
    set_frozen_digest(digest)
    return digest


def manifest_memory_fields(workdir: Path, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    label = memory_sharing_label(env)
    frozen = bootstrap_frozen_digest(workdir, env) if label == "frozen_active" else None
    out: dict[str, Any] = {"memory_sharing": label}
    if frozen:
        out["memory_digest_frozen"] = frozen
    return out
