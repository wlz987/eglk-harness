"""Local Environment — process-group aware CLI runner (LH-shaped)."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from eglk_harness.domain.environment.base import ExecResult
from eglk_harness.domain.environment import process_group as pg

# Raise StreamReader limit so screenshot-sized JSON lines survive (LH note).
_STREAM_LIMIT = 64 * 1024 * 1024


class LocalEnvironment:
    async def exec(
        self,
        command: list[str] | str,
        *,
        cwd: str | None = None,
        stdin_text: str = "",
        timeout_s: float = 600.0,
        env: dict[str, str] | None = None,
        tee_path: str | None = None,
    ) -> ExecResult:
        merged = dict(os.environ)
        if env:
            merged.update(env)
        start = time.monotonic()
        if isinstance(command, str):
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merged,
                start_new_session=True,
                limit=_STREAM_LIMIT,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merged,
                start_new_session=True,
                limit=_STREAM_LIMIT,
            )
        assert proc.pid is not None
        pg.track_process_group(proc.pid)
        tee_file = None
        if tee_path:
            Path(tee_path).parent.mkdir(parents=True, exist_ok=True)
            tee_file = open(tee_path, "w", encoding="utf-8")  # noqa: SIM115

        async def _pump(reader: asyncio.StreamReader, chunks: list[bytes], *, mirror: bool) -> None:
            while True:
                line = await reader.readline()
                if not line:
                    break
                chunks.append(line)
                if mirror and tee_file is not None:
                    try:
                        from eglk_harness.domain.runtime.redact import redact_secrets

                        tee_file.write(redact_secrets(line.decode("utf-8", errors="replace")))
                        tee_file.flush()
                    except OSError:
                        pass

        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        try:
            assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
            if stdin_text:
                proc.stdin.write(stdin_text.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()
            pump_out = asyncio.create_task(_pump(proc.stdout, out_chunks, mirror=True))
            pump_err = asyncio.create_task(_pump(proc.stderr, err_chunks, mirror=True))
            try:
                await asyncio.wait_for(
                    asyncio.gather(pump_out, pump_err, proc.wait()),
                    timeout=timeout_s,
                )
            except TimeoutError:
                pump_out.cancel()
                pump_err.cancel()
                pg.kill_process_group(proc.pid)
                await proc.wait()
                raise
            stdout = b"".join(out_chunks).decode("utf-8", errors="replace")
            stderr = b"".join(err_chunks).decode("utf-8", errors="replace")
            return ExecResult(
                returncode=int(proc.returncode or 0),
                stdout=stdout,
                stderr=stderr,
                duration_s=time.monotonic() - start,
            )
        finally:
            pg.untrack_process_group(proc.pid)
            if tee_file is not None:
                tee_file.close()


_DEFAULT = LocalEnvironment()


def default_environment() -> LocalEnvironment:
    return _DEFAULT
