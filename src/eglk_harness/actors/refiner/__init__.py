"""Refiner actor — writes sigma/refined/ only; never touches Gate inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eba import RequestResponseActor

from eglk_harness.domain import sigma
from eglk_harness.protocol import messages, payload, topics


class RefinerActor(RequestResponseActor):
    pattern = f"{topics.ROLE_REFINER_RUN}.*"
    result_prefix = topics.ROLE_REFINER_RESULT
    error_code = "refiner_failed"

    def __init__(self, **kwargs: Any) -> None:
        if kwargs.pop("mcp_config", None) or kwargs.pop("add_dirs", None):
            raise AssertionError("Refiner must not receive MCP")
        if kwargs.pop("tools_allowed", False):
            raise AssertionError("Refiner tools_allowed must be False")
        super().__init__(**kwargs)

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        decision = str(args.get("decision") or "")
        reason = str(args.get("reason") or "")
        if decision == "abort":
            item = {
                "id": f"sigma-abort-{tick:03d}",
                "kind": "archive",
                "decision": decision,
                "reason": reason,
                "conf": 0.5,
            }
        elif decision == "repair":
            item = {
                "id": f"sigma-lesson-{tick:03d}",
                "kind": "lesson",
                "cond": reason,
                "text": f"repair:{reason}",
                "conf": 0.6,
            }
        else:
            item = {
                "id": f"sigma-hit-{tick:03d}",
                "kind": "hit",
                "text": "admit reinforced",
                "conf": 0.7,
            }
        path = sigma.write_refined(loop_dir, tick, item)
        # Authority stays in memory/ — refined is staging only
        return messages.ok_body(refined=item, path=str(path))
