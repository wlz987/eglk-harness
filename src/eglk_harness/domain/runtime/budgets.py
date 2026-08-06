"""Per-role episode duration budgets (timeouts)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EpisodeBudget:
    max_duration_seconds: float = 600.0


@dataclass(frozen=True)
class RoleBudgets:
    maker: EpisodeBudget = EpisodeBudget(600.0)
    checker: EpisodeBudget = EpisodeBudget(600.0)
    governor: EpisodeBudget = EpisodeBudget(120.0)
    explorer: EpisodeBudget = EpisodeBudget(120.0)
    verifier: EpisodeBudget = EpisodeBudget(120.0)
    refiner: EpisodeBudget = EpisodeBudget(120.0)
    compile: EpisodeBudget = EpisodeBudget(180.0)

    def for_role(self, role: str) -> EpisodeBudget:
        return getattr(self, role, EpisodeBudget(120.0))


_ENV_KEYS = {
    "maker": "EGLK_TIMEOUT_MAKER",
    "checker": "EGLK_TIMEOUT_CHECKER",
    "governor": "EGLK_TIMEOUT_GOVERNOR",
    "explorer": "EGLK_TIMEOUT_EXPLORER",
    "verifier": "EGLK_TIMEOUT_VERIFIER",
    "refiner": "EGLK_TIMEOUT_REFINER",
    "compile": "EGLK_TIMEOUT_COMPILE",
}


def resolve_role_budgets(
    args_ns: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> RoleBudgets:
    """CLI timeouts win over env; env wins over defaults."""
    env = env or os.environ
    defaults = RoleBudgets()
    values: dict[str, float] = {
        "maker": defaults.maker.max_duration_seconds,
        "checker": defaults.checker.max_duration_seconds,
        "governor": defaults.governor.max_duration_seconds,
        "explorer": defaults.explorer.max_duration_seconds,
        "verifier": defaults.verifier.max_duration_seconds,
        "refiner": defaults.refiner.max_duration_seconds,
        "compile": defaults.compile.max_duration_seconds,
    }
    for role, key in _ENV_KEYS.items():
        raw = env.get(key)
        if raw:
            try:
                values[role] = float(raw)
            except ValueError:
                pass
    if args_ns is not None:
        maker = getattr(args_ns, "maker_timeout", None)
        checker = getattr(args_ns, "checker_timeout", None)
        if maker is not None:
            values["maker"] = float(maker)
        if checker is not None:
            values["checker"] = float(checker)
        for role in ("governor", "explorer", "verifier", "refiner", "compile"):
            attr = f"{role}_timeout"
            val = getattr(args_ns, attr, None)
            if val is not None:
                values[role] = float(val)
    return RoleBudgets(
        maker=EpisodeBudget(values["maker"]),
        checker=EpisodeBudget(values["checker"]),
        governor=EpisodeBudget(values["governor"]),
        explorer=EpisodeBudget(values["explorer"]),
        verifier=EpisodeBudget(values["verifier"]),
        refiner=EpisodeBudget(values["refiner"]),
        compile=EpisodeBudget(values["compile"]),
    )


def timeout_for_role(role: str, env: Mapping[str, str] | None = None) -> float:
    """Resolve one role's episode timeout from env/defaults (for bypass actors)."""
    return resolve_role_budgets(None, env).for_role(role.lower()).max_duration_seconds
