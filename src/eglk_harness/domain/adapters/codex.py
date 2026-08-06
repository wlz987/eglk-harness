"""Codex CLI AgentAdapter (default backend)."""

from __future__ import annotations

import os
from pathlib import Path

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.adapters import mcp as mcp_mod
from eglk_harness.domain.adapters.codex_overrides import provider_overrides
from eglk_harness.domain.adapters.parse import episode_from_text
from eglk_harness.domain.adapters.process import require_binary, run_cli


class CodexAdapter:
    name = "codex"

    def __init__(
        self,
        *,
        model: str | None = None,
        mcp_config: Path | None = None,
        add_dirs: list[str] | None = None,
        binary: str = "codex",
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("EGLK_MODEL") or None
        self.mcp_config = mcp_config
        self.add_dirs = list(add_dirs or [])
        self.binary = binary
        self.base_url = base_url
        self.api_key = api_key

    def build_argv(self, request: EpisodeRequest) -> list[str]:
        bin_path = require_binary(self.binary)
        argv: list[str] = [
            bin_path,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        model = request.model or self.model
        if model:
            argv.extend(["--model", model])

        for override in provider_overrides(base_url=self.base_url, api_key=self.api_key):
            argv.extend(["-c", override])

        mcp_path = request.mcp_config or self.mcp_config
        add_dirs = list(request.add_dirs) or list(self.add_dirs)
        # Prefer package mcp translator; also emit -c mcp_servers when path set
        argv.extend(
            mcp_mod.codex_mcp_argv(
                mcp_config=mcp_path,
                add_dirs=add_dirs,
                tools_allowed=request.tools_allowed,
                role=request.role,
            )
        )

        argv.append("-")  # prompt on stdin
        return argv

    async def run_episode(self, request: EpisodeRequest) -> EpisodeResult:
        try:
            argv = self.build_argv(request)
        except (FileNotFoundError, AssertionError) as exc:
            return EpisodeResult(ok=False, error=str(exc), backend=self.name)

        env: dict[str, str] | None = None
        key = self.api_key or os.environ.get("EGLK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if key:
            env = {"OPENAI_API_KEY": key, "CODEX_API_KEY": key}

        try:
            proc = await run_cli(
                argv,
                cwd=request.workdir,
                stdin_text=request.prompt,
                timeout_s=request.timeout_s,
                env=env,
                tee_path=request.tee_path,
            )
        except TimeoutError:
            return EpisodeResult(ok=False, error="codex_timeout", backend=self.name)

        text = proc.stdout or proc.stderr
        if proc.returncode != 0 and not proc.stdout.strip():
            return EpisodeResult(
                ok=False,
                text=text,
                error=f"codex_exit_{proc.returncode}: {proc.stderr[:500]}",
                backend=self.name,
            )
        from eglk_harness.domain.adapters.agent_logs import write_trajectory_sidecars

        write_trajectory_sidecars(request.tee_path, text)
        return episode_from_text(request, text, backend=self.name)
