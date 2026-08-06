"""Environment protocol for Adapter subprocess execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ExecResult:
    returncode: int
    stdout: str
    stderr: str
    duration_s: float = 0.0


@runtime_checkable
class Environment(Protocol):
    async def exec(
        self,
        command: list[str] | str,
        *,
        cwd: str | None = None,
        stdin_text: str = "",
        timeout_s: float = 600.0,
        env: dict[str, str] | None = None,
        tee_path: str | None = None,
    ) -> ExecResult: ...
