"""Resolve CLI / config.toml / env defaults (non-secret).

Priority (packaging.md): explicit CLI > config.toml > env > built-in.
``runtime_bootstrap.bootstrap_workdir`` materializes config into ``os.environ``
before these helpers run, so env lookups already reflect config.
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
    # After bootstrap, EGLK_AGENT already includes config.toml [run].default_agent
    if env.get("EGLK_AGENT", "").strip():
        return str(env["EGLK_AGENT"]).strip()
    cfg = load_config_toml(workdir)
    run = cfg.get("run") if isinstance(cfg.get("run"), dict) else {}
    default = str(run.get("default_agent") or "").strip()
    return default or "mock"


def resolve_swarm(
    cli: str | None,
    workdir: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    env = env or os.environ
    if cli is not None:
        return str(cli).strip()
    if env.get("EGLK_SWARM", "").strip() != "":
        return str(env["EGLK_SWARM"]).strip()
    if workdir is not None:
        cfg = load_config_toml(workdir)
        run = cfg.get("run") if isinstance(cfg.get("run"), dict) else {}
        if run.get("swarm") is not None and str(run.get("swarm")).strip() != "":
            return str(run["swarm"]).strip()
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


def resolve_mcp_from_config(workdir: Path) -> Path | None:
    cfg = load_config_toml(workdir)
    mcp = cfg.get("mcp") if isinstance(cfg.get("mcp"), dict) else {}
    raw = mcp.get("config")
    return Path(str(raw)) if raw else None
