"""Resolve CLI / env / config.toml defaults (non-secret).

Priority: explicit CLI > env > config.toml > built-in default.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain import paths


def load_config_toml(workdir: Path) -> dict[str, Any]:
    cfg = paths.config_path(workdir)
    if not cfg.is_file():
        return {}
    with cfg.open("rb") as f:
        data = tomllib.load(f)
    return data if isinstance(data, dict) else {}


def resolve_agent(
    cli: str | None, workdir: Path, *, env: Mapping[str, str] | None = None
) -> str:
    env = env or os.environ
    if cli is not None and str(cli).strip():
        return str(cli).strip()
    if env.get("EGLK_AGENT", "").strip():
        return str(env["EGLK_AGENT"]).strip()
    cfg = load_config_toml(workdir)
    run = cfg.get("run") if isinstance(cfg.get("run"), dict) else {}
    default = str(run.get("default_agent") or "").strip()
    return default or "mock"


def resolve_swarm(cli: str | None, *, env: Mapping[str, str] | None = None) -> str | None:
    env = env or os.environ
    if cli is not None:
        return str(cli).strip()
    if env.get("EGLK_SWARM", "").strip() != "":
        return str(env["EGLK_SWARM"]).strip()
    return None


def resolve_compile(
    cli: str | None, workdir: Path, *, env: Mapping[str, str] | None = None
) -> str | None:
    env = env or os.environ
    if cli is not None:
        return str(cli).strip()
    if env.get("EGLK_COMPILE", "").strip():
        return str(env["EGLK_COMPILE"]).strip()
    cfg = load_config_toml(workdir)
    run = cfg.get("run") if isinstance(cfg.get("run"), dict) else {}
    val = run.get("compile")
    return str(val).strip() if val else None
