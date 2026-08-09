"""Shared CLI subprocess runner for Codex / Claude adapters."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from eglk_harness.domain.environment.local import LocalEnvironment, default_environment
from eglk_harness.domain.runtime.redact import redact_secrets


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str


async def run_cli(
    argv: list[str],
    *,
    cwd: Path,
    stdin_text: str = "",
    timeout_s: float = 600.0,
    env: dict[str, str] | None = None,
    environment: LocalEnvironment | None = None,
    tee_path: str | None = None,
) -> ProcResult:
    env_runner = environment or default_environment()
    result = await env_runner.exec(
        argv,
        cwd=str(cwd),
        stdin_text=stdin_text,
        timeout_s=timeout_s,
        env=env,
        tee_path=tee_path,
    )
    return ProcResult(
        returncode=result.returncode,
        stdout=redact_secrets(result.stdout),
        stderr=redact_secrets(result.stderr),
    )


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"{name} not found in PATH")
    return path
