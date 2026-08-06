"""Phase-0 SWARM workers: Explorer / Verifier / Pruner — candidates/ only; zero MCP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eba import RequestResponseActor

from eglk_harness.protocol import messages, payload, topics


def _ban_tools(kwargs: dict[str, Any]) -> dict[str, Any]:
    if kwargs.pop("mcp_config", None) or kwargs.pop("add_dirs", None):
        raise AssertionError("SWARM roles must not receive MCP")
    if kwargs.pop("tools_allowed", False):
        raise AssertionError("SWARM tools_allowed must be False")
    return kwargs


def _write_candidate(loop_dir: Path, name: str, doc: dict[str, Any]) -> Path:
    cand = loop_dir / "candidates"
    cand.mkdir(parents=True, exist_ok=True)
    path = cand / name
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


class ExplorerActor(RequestResponseActor):
    pattern = f"{topics.ROLE_EXPLORER_RUN}.*"
    result_prefix = topics.ROLE_EXPLORER_RESULT
    error_code = "explorer_failed"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**_ban_tools(kwargs))

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        leaf = str(args.get("subgoal_id") or "root")
        doc = {
            "role": "explorer",
            "tick": tick,
            "leaf_id": leaf,
            "alternatives": [
                {"id": "alt-1", "text": "write hello.txt directly", "prob": 0.8, "impact": 0.9},
                {"id": "alt-2", "text": "defer file write", "prob": 0.2, "impact": 0.1},
            ],
        }
        _write_candidate(loop_dir, f"explorer_{tick:03d}.json", doc)
        return messages.ok_body(artifact=doc)


class VerifierActor(RequestResponseActor):
    pattern = f"{topics.ROLE_VERIFIER_RUN}.*"
    result_prefix = topics.ROLE_VERIFIER_RESULT
    error_code = "verifier_failed"

    def __init__(self, *, audit: bool = False, **kwargs: Any) -> None:
        super().__init__(**_ban_tools(kwargs))
        self.audit = audit  # Phase-2 veto uses same actor with audit=True via payload

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        leaf = str(args.get("subgoal_id") or "root")
        is_audit = bool(args.get("veto_audit") or self.audit)
        doc = {
            "role": "verifier_audit" if is_audit else "verifier",
            "tick": tick,
            "leaf_id": leaf,
            "challenges": [
                {"id": "ch-1", "title": "file may be empty", "text": "ensure non-empty hello.txt"},
            ],
            "veto": False,
        }
        name = f"verifier_audit_{tick:03d}.json" if is_audit else f"verifier_{tick:03d}.json"
        _write_candidate(loop_dir, name, doc)
        return messages.ok_body(artifact=doc)


class PrunerActor(RequestResponseActor):
    pattern = f"{topics.ROLE_PRUNER_RUN}.*"
    result_prefix = topics.ROLE_PRUNER_RESULT
    error_code = "pruner_failed"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**_ban_tools(kwargs))

    async def work(self, body: Any) -> Any:
        args = payload.get_args(body if isinstance(body, dict) else {})
        loop_dir = Path(str(args["loop_dir"]))
        tick = int(args.get("tick", 0))
        # Read explorer if present and mark low value pruned
        explorer_path = loop_dir / "candidates" / f"explorer_{tick:03d}.json"
        alts: list[dict[str, Any]] = []
        if explorer_path.is_file():
            raw = json.loads(explorer_path.read_text(encoding="utf-8"))
            for a in raw.get("alternatives") or []:
                if not isinstance(a, dict):
                    continue
                score = float(a.get("prob", 0)) * float(a.get("impact", 0))
                entry = dict(a)
                entry["score"] = score
                entry["pruned"] = score < 0.2
                alts.append(entry)
        doc = {"role": "pruner", "tick": tick, "alternatives": alts}
        _write_candidate(loop_dir, f"pruner_{tick:03d}.json", doc)
        return messages.ok_body(artifact=doc)
