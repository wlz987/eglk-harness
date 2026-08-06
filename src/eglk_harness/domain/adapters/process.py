"""Shared CLI subprocess runner for Codex / Claude adapters."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


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
) -> ProcResult:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=merged,
    )
    try:
        out_b, err_b = await asyncio.wait_for(
            proc.communicate(stdin_text.encode("utf-8") if stdin_text else None),
            timeout=timeout_s,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return ProcResult(
        returncode=int(proc.returncode or 0),
        stdout=out_b.decode("utf-8", errors="replace"),
        stderr=err_b.decode("utf-8", errors="replace"),
    )


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"{name} not found in PATH")
    return path
