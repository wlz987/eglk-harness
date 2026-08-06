"""Governor actor — tree structure only; zero MCP/tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eba import RequestResponseActor

from eglk_harness.domain.adapters.base import AgentAdapter
from eglk_harness.domain.bypass_llm import coerce_governor_proposal, run_bypass_json
from eglk_harness.domain.governor_split import proposal_document
from eglk_harness.domain.loop_store import load_tree
from eglk_harness.protocol import messages, payload, topics


class GovernorActor(RequestResponseActor):
    pattern = f"{topics.ROLE_GOVERNOR_RUN}.*"
    result_prefix = topics.ROLE_GOVERNOR_RESULT
    error_code = "governor_failed"

    def __init__(
        self,
        *,
        workdir: Path | None = None,
        adapter: AgentAdapter | None = None,
        **kwargs: Any,
    ) -> None:
        if kwargs.pop("mcp_config", None) or kwargs.pop("add_dirs", None):
            raise AssertionError("Governor must not receive MCP")
        if kwargs.pop("tools_allowed", False):
            raise AssertionError("Governor tools_allowed must be False")
        super().__init__(**kwargs)
        self.workdir = Path(workdir).resolve() if workdir else Path.cwd()
        self.adapter = adapter

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        loop_dir = Path(str(args["loop_dir"])) if args.get("loop_dir") else None
        tick = int(args.get("tick", 0))
        leaf_id = str(args.get("subgoal_id") or "root")
        title = str(args.get("goal_title") or leaf_id)
        criteria = [str(x) for x in (args.get("done_criteria") or [])]
        streak = int(args.get("repair_streak") or 0)
        workdir = Path(args.get("workdir") or self.workdir).resolve()

        if loop_dir is not None and (not criteria or title == leaf_id):
            tree = load_tree(loop_dir)
            if tree is not None:
                node = tree.find(leaf_id)
                if node is not None:
                    title = node.title or title
                    criteria = list(node.done_criteria) or criteria
                    streak = int(node.repair_streak or streak)

        fallback = proposal_document(
            tick=tick,
            leaf_id=leaf_id,
            title=title,
            done_criteria=criteria,
            repair_streak=streak,
        )
        leaf_block = (
            f"[LEAF]\nid: {leaf_id}\ntitle: {title}\n"
            f"repair_streak: {streak}\nacceptance:\n"
            + "\n".join(f"  - {c}" for c in criteria)
        )
        raw = await run_bypass_json(
            self.adapter,
            role="governor",
            workdir=workdir,
            leaf_block=leaf_block,
            extra='JSON shape: {"split_node":"...","children":[{"id","title","done_criteria":[]}]}',
            tick=tick,
            subgoal_id=leaf_id,
        )
        proposal = coerce_governor_proposal(raw, tick=tick, leaf_id=leaf_id, fallback=fallback)
        if loop_dir is not None:
            cand = loop_dir / "candidates"
            cand.mkdir(parents=True, exist_ok=True)
            (cand / "subgoals_tree.json").write_text(
                json.dumps(proposal, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return messages.ok_body(proposal=proposal)
