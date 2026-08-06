"""Checker role actor — Adapter episode → Evidence JSON (read-only intent)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eba import RequestResponseActor

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.format_repair import run_with_format_repair
from eglk_harness.domain.leaf_contract import LeafContract
from eglk_harness.domain.models import resolve_model
from eglk_harness.domain.skills import render_prompt
from eglk_harness.protocol import messages, payload, topics


class CheckerActor(RequestResponseActor):
    pattern = f"{topics.ROLE_CHECKER_RUN}.*"
    result_prefix = topics.ROLE_CHECKER_RESULT
    error_code = "checker_failed"

    def __init__(
        self,
        *,
        adapter: AgentAdapter | None = None,
        workdir: Path | None = None,
        tools_allowed: bool = True,
        mcp_config: Path | None = None,
        add_dirs: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not tools_allowed and (mcp_config or add_dirs):
            raise AssertionError("Checker MCP requires tools_allowed=True")
        self.adapter: AgentAdapter = adapter or MockAdapter()
        self.workdir = Path(workdir).resolve() if workdir else Path.cwd()
        self.tools_allowed = tools_allowed
        self.mcp_config = mcp_config
        self.add_dirs = tuple(add_dirs or ())

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        tick = int(args.get("tick", 0))
        claim = args.get("claim") if isinstance(args.get("claim"), dict) else {}
        subgoal_id = str(args.get("subgoal_id") or claim.get("subgoal_id") or "root")
        written = list(args.get("written") or [])
        criteria = [str(x) for x in (args.get("done_criteria") or ["done"])]
        title = str(args.get("goal_title") or args.get("title") or subgoal_id)
        workdir = Path(args.get("workdir") or self.workdir).resolve()
        tee_path = args.get("tee_path")

        leaf = LeafContract(
            leaf_id=subgoal_id,
            goal=title,
            acceptance=criteria,
            tick=tick,
        )
        leaf_block = leaf.render_checker_block()
        extra = (
            f"Maker claim:\n```json\n{claim}\n```\n"
            f"Applied paths: {written}\n"
            "Inspect the workdir; do not modify files."
        )
        prompt = render_prompt("checker", leaf_block=leaf_block, extra=extra)
        request = EpisodeRequest(
            role="checker",
            prompt=prompt,
            workdir=workdir,
            tools_allowed=self.tools_allowed,
            mcp_config=self.mcp_config if self.tools_allowed else None,
            add_dirs=self.add_dirs if self.tools_allowed else (),
            expect="evidence",
            model=resolve_model("checker"),
            timeout_s=float(args.get("timeout_s") or 600.0),
            meta={"tick": tick, "subgoal_id": subgoal_id, "written": written, "claim": claim},
            tee_path=str(tee_path) if tee_path else None,
        )
        result = await run_with_format_repair(
            self.adapter, request, leaf_block=f"{leaf_block}\n\n{extra}"
        )
        if not result.ok or not isinstance(result.parsed, dict):
            return messages.err_body(result.error or "checker_episode_failed")
        evidence = dict(result.parsed)
        evidence["tick"] = tick
        evidence["subgoal_id"] = subgoal_id
        return messages.ok_body(
            evidence=evidence,
            tokens=int(result.tokens or 0),
            cost_usd=float(result.cost_usd or 0.0),
        )
