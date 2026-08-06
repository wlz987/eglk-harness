"""Claude Code AgentAdapter (first-class peer to Codex)."""

from __future__ import annotations

import os
from pathlib import Path

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.adapters import mcp as mcp_mod
from eglk_harness.domain.adapters.process import require_binary, run_cli
from eglk_harness.domain.schema_validate import parse_and_validate


class ClaudeCodeAdapter:
    name = "claude_code"

    def __init__(
        self,
        *,
        model: str | None = None,
        mcp_config: Path | None = None,
        add_dirs: list[str] | None = None,
        binary: str = "claude",
    ) -> None:
        self.model = model or os.environ.get("EGLK_MODEL") or None
        self.mcp_config = mcp_config
        self.add_dirs = list(add_dirs or [])
        self.binary = binary

    def build_argv(self, request: EpisodeRequest) -> list[str]:
        bin_path = require_binary(self.binary)
        # print mode: non-interactive; prompt as final arg
        argv: list[str] = [bin_path, "-p", "--output-format", "text"]
        model = request.model or self.model
        if model:
            argv.extend(["--model", model])

        mcp_path = request.mcp_config or self.mcp_config
        add_dirs = list(request.add_dirs) or list(self.add_dirs)
        argv.extend(
            mcp_mod.claude_mcp_argv(
                mcp_config=mcp_path,
                add_dirs=add_dirs,
                tools_allowed=request.tools_allowed,
                role=request.role,
            )
        )
        argv.append(request.prompt)
        return argv

    async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
        try:
            argv = self.build_argv(request)
        except FileNotFoundError as exc:
            return EpisodeResult(ok=False, error=str(exc), backend=self.name)
        except AssertionError as exc:
            return EpisodeResult(ok=False, error=str(exc), backend=self.name)

        try:
            proc = await run_cli(
                argv,
                cwd=request.workdir,
                timeout_s=request.timeout_s,
            )
        except TimeoutError:
            return EpisodeResult(ok=False, error="claude_timeout", backend=self.name)

        text = proc.stdout or proc.stderr
        if proc.returncode != 0 and not proc.stdout.strip():
            return EpisodeResult(
                ok=False,
                text=text,
                error=f"claude_exit_{proc.returncode}: {proc.stderr[:500]}",
                backend=self.name,
            )
        return self._parse(request, text)

    def _parse(self, request: EpisodeRequest, text: str) -> EpisodeResult:
        if request.expect == "text":
            return EpisodeResult(ok=True, text=text, backend=self.name)
        schema = "claim" if request.expect == "claim" else "evidence"
        parsed, errs = parse_and_validate(schema, text)
        if errs or parsed is None:
            return EpisodeResult(
                ok=False,
                text=text,
                error="unparseable:" + ";".join(errs),
                backend=self.name,
            )
        return EpisodeResult(ok=True, text=text, parsed=parsed, backend=self.name)
