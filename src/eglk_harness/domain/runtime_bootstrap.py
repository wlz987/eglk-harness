"""Bootstrap workdir runtime: dotenv → config.toml → CLI (packaging.md priority).

Priority (design/kernel/packaging.md §3.2)::

    explicit CLI  >  .eglk-harness/config.toml  >  .env / process env  >  built-in
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from eglk_harness.domain.config_resolve import load_config_toml


def load_dotenv_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE ``.env`` (no export, no nested quotes expansion)."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def apply_dotenv(workdir: Path, *, environ: dict[str, str] | None = None) -> list[str]:
    """Fill missing keys from ``workdir/.env`` (does not override existing)."""
    env = environ if environ is not None else os.environ  # type: ignore[assignment]
    applied: list[str] = []
    for key, val in load_dotenv_file(Path(workdir) / ".env").items():
        if key not in env or not str(env.get(key) or "").strip():
            env[key] = val
            applied.append(key)
    return applied


def apply_config_toml(workdir: Path, *, environ: dict[str, str] | None = None) -> list[str]:
    """Project config overrides env for non-secret run settings (config > env)."""
    env = environ if environ is not None else os.environ  # type: ignore[assignment]
    cfg = load_config_toml(Path(workdir))
    applied: list[str] = []

    def _set(key: str, value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        env[key] = text
        applied.append(key)

    run = cfg.get("run") if isinstance(cfg.get("run"), dict) else {}
    if run.get("default_agent"):
        _set("EGLK_AGENT", run["default_agent"])
    if run.get("compile"):
        _set("EGLK_COMPILE", run["compile"])
    if run.get("swarm") is not None and str(run.get("swarm")).strip() != "":
        _set("EGLK_SWARM", run["swarm"])

    models = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    role_map = {
        "maker": "EGLK_MODEL_MAKER",
        "checker": "EGLK_MODEL_CHECKER",
        "governor": "EGLK_MODEL_GOVERNOR",
        "explorer": "EGLK_MODEL_EXPLORER",
        "verifier": "EGLK_MODEL_VERIFIER",
        "pruner": "EGLK_MODEL_PRUNER",
        "refiner": "EGLK_MODEL_REFINER",
        "compile": "EGLK_MODEL_COMPILE",
    }
    for role, env_key in role_map.items():
        if models.get(role):
            _set(env_key, models[role])
    if models.get("default") or models.get("shared"):
        _set("EGLK_MODEL", models.get("default") or models.get("shared"))

    limits = cfg.get("limits") if isinstance(cfg.get("limits"), dict) else {}
    if limits.get("cognitive_tokens_max") is not None:
        _set("EGLK_COGNITIVE_TOKENS_MAX", limits["cognitive_tokens_max"])
    if limits.get("repairs_max") is not None:
        _set("EGLK_REPAIRS_MAX", limits["repairs_max"])
    if limits.get("max_ticks_soft") is not None:
        _set("EGLK_MAX_TICKS_SOFT", limits["max_ticks_soft"])

    budgets = cfg.get("budgets") if isinstance(cfg.get("budgets"), dict) else {}
    budget_map = {
        "maker": "EGLK_TIMEOUT_MAKER",
        "checker": "EGLK_TIMEOUT_CHECKER",
        "governor": "EGLK_TIMEOUT_GOVERNOR",
        "explorer": "EGLK_TIMEOUT_EXPLORER",
        "verifier": "EGLK_TIMEOUT_VERIFIER",
        "refiner": "EGLK_TIMEOUT_REFINER",
        "compile": "EGLK_TIMEOUT_COMPILE",
    }
    for role, env_key in budget_map.items():
        if budgets.get(role) is not None:
            _set(env_key, budgets[role])

    mcp = cfg.get("mcp") if isinstance(cfg.get("mcp"), dict) else {}
    if mcp.get("config"):
        _set("EGLK_MCP_CONFIG", mcp["config"])
    add_dirs = mcp.get("add_dirs")
    if isinstance(add_dirs, list) and add_dirs:
        _set("EGLK_MCP_ADD_DIRS", os.pathsep.join(str(x) for x in add_dirs))

    observe = cfg.get("observe") if isinstance(cfg.get("observe"), dict) else {}
    if observe.get("prompt_language"):
        _set("EGLK_PROMPT_LANGUAGE", observe["prompt_language"])
    if "dashboard" in observe:
        _set("EGLK_DASHBOARD", "1" if observe.get("dashboard") else "0")

    return applied


def bootstrap_workdir(workdir: Path, *, cli_env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Apply dotenv then config.toml; finally CLI env overrides. Mutates ``os.environ``."""
    dotenv_keys = apply_dotenv(workdir)
    config_keys = apply_config_toml(workdir)
    cli_applied: list[str] = []
    for key, val in dict(cli_env or {}).items():
        if val is None or str(val).strip() == "":
            continue
        os.environ[key] = str(val)
        cli_applied.append(key)
    return {
        "dotenv": dotenv_keys,
        "config": config_keys,
        "cli": cli_applied,
    }


def want_dashboard(*, cli_flag: bool | None = None, env: Mapping[str, str] | None = None) -> bool:
    """Whether to open the read-only dashboard after (or with) a run."""
    if cli_flag is True:
        return True
    if cli_flag is False:
        return False
    env = env or os.environ
    raw = (env.get("EGLK_DASHBOARD") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def soft_max_ticks(cli: int | None = None, *, env: Mapping[str, str] | None = None) -> int | None:
    if cli is not None:
        return int(cli)
    env = env or os.environ
    raw = (env.get("EGLK_MAX_TICKS_SOFT") or "").strip()
    if not raw:
        return None
    try:
        val = int(raw)
    except ValueError:
        return None
    return val if val > 0 else None
