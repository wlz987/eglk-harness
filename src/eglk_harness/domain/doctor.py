"""Read-only environment checks for ``eglk-harness doctor``."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from eglk_harness import __version__
from eglk_harness.domain import paths
from eglk_harness.domain.adapters.mcp import resolve_mcp_config
from eglk_harness.domain.paths import STATE_SCHEMA
from eglk_harness.domain.skills import load_skill


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class DoctorReport:
    checks: list[DoctorCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def run_doctor(workdir: Path | None = None) -> DoctorReport:
    """Inspect environment only — never install plugins or mutate GUI state."""
    report = DoctorReport()
    workdir = (workdir or Path.cwd()).resolve()

    report.checks.append(
        DoctorCheck(
            name="python",
            ok=sys.version_info >= (3, 11),
            detail=f"{sys.version.split()[0]} (need >=3.11); package {__version__}",
        )
    )

    codex = shutil.which("codex")
    report.checks.append(
        DoctorCheck(
            name="codex",
            ok=True,
            detail=("found in PATH" if codex else "not in PATH [warn] — needed for --agent codex"),
        )
    )
    claude = shutil.which("claude")
    report.checks.append(
        DoctorCheck(
            name="claude",
            ok=True,
            detail=(
                "found in PATH" if claude else "not in PATH [warn] — needed for --agent claude_code"
            ),
        )
    )

    schema_dir = Path(__file__).resolve().parent / "schemas"
    required = ("state.schema.json", "claim.schema.json", "evidence.schema.json", "gate_decision.schema.json")
    missing = [n for n in required if not (schema_dir / n).is_file()]
    report.checks.append(
        DoctorCheck(
            name="schemas",
            ok=not missing,
            detail=(
                f"pin {STATE_SCHEMA}; dir={schema_dir}"
                if not missing
                else f"missing {missing} under {schema_dir}"
            ),
        )
    )

    try:
        load_skill("maker")
        load_skill("checker")
        skills_ok, skills_detail = True, "maker.md + checker.md present"
    except FileNotFoundError as exc:
        skills_ok, skills_detail = False, str(exc)
    report.checks.append(DoctorCheck(name="skills", ok=skills_ok, detail=skills_detail))

    mcp = resolve_mcp_config(None)
    if mcp is None:
        report.checks.append(
            DoctorCheck(name="mcp_config", ok=True, detail="unset (opt-in; no MCP)")
        )
    elif not mcp.is_file():
        report.checks.append(
            DoctorCheck(name="mcp_config", ok=False, detail=f"EGLK_MCP_CONFIG not readable: {mcp}")
        )
    else:
        try:
            data = json.loads(mcp.read_text(encoding="utf-8"))
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            n = len(servers) if isinstance(servers, dict) else 0
            report.checks.append(
                DoctorCheck(name="mcp_config", ok=True, detail=f"{mcp} readable; {n} server(s)")
            )
        except (OSError, json.JSONDecodeError) as exc:
            report.checks.append(
                DoctorCheck(name="mcp_config", ok=False, detail=f"invalid JSON: {exc}")
            )

    harness = paths.harness_root(workdir)
    report.checks.append(
        DoctorCheck(
            name="workdir_harness",
            ok=True,
            detail=(
                f"{harness} present"
                if harness.is_dir()
                else f"{harness} absent (run `eglk-harness init`)"
            ),
        )
    )

    report.checks.append(
        DoctorCheck(
            name="package",
            ok=importlib.util.find_spec("eglk_harness") is not None,
            detail="eglk_harness importable",
        )
    )

    return report
