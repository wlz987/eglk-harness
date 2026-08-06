"""Governor actor — tree structure only; zero MCP/tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eba import RequestResponseActor

from eglk_harness.protocol import messages, payload, topics


class GovernorActor(RequestResponseActor):
    pattern = f"{topics.ROLE_GOVERNOR_RUN}.*"
    result_prefix = topics.ROLE_GOVERNOR_RESULT
    error_code = "governor_failed"

    def __init__(self, *, workdir: Path | None = None, **kwargs: Any) -> None:
        # Hard: no MCP kwargs accepted on construction
        if kwargs.pop("mcp_config", None) or kwargs.pop("add_dirs", None):
            raise AssertionError("Governor must not receive MCP")
        if kwargs.pop("tools_allowed", False):
            raise AssertionError("Governor tools_allowed must be False")
        super().__init__(**kwargs)
        self.workdir = Path(workdir).resolve() if workdir else Path.cwd()

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        loop_dir = Path(str(args["loop_dir"])) if args.get("loop_dir") else None
        tick = int(args.get("tick", 0))
        leaf_id = str(args.get("subgoal_id") or "root")
        # Mock split proposal — orchestrator applies via tree.split_node
        children = [
            {
                "id": f"{leaf_id}.a",
                "title": f"{leaf_id} part A",
                "done_criteria": ["part A done"],
            },
            {
                "id": f"{leaf_id}.b",
                "title": f"{leaf_id} part B",
                "done_criteria": ["part B done"],
            },
        ]
        proposal = {
            "role": "governor",
            "tick": tick,
            "split_node": leaf_id,
            "children": children,
        }
        if loop_dir is not None:
            cand = loop_dir / "candidates"
            cand.mkdir(parents=True, exist_ok=True)
            (cand / "subgoals_tree.json").write_text(
                __import__("json").dumps(proposal, indent=2) + "\n",
                encoding="utf-8",
            )
        return messages.ok_body(proposal=proposal)
