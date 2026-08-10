"""Maker role actor — Adapter episode → Claim JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from eba import Worker

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.runtime.format_repair import run_with_format_repair
from eglk_harness.domain.kernel.leaf_contract import LeafContract, contract_from_dict
from eglk_harness.domain.runtime.models import resolve_model
from eglk_harness.domain.memory.skills import render_prompt
from eglk_harness.protocol import messages, payload, topics

def _leaf_from_args(args: Mapping[str, Any], *, tick: int, subgoal_id: str, criteria: list[str], title: str) -> LeafContract:
    lc = args.get("leaf_contract")
    if isinstance(lc, dict):
        leaf = contract_from_dict(lc)
        if leaf.leaf_id == "root" and subgoal_id != "root":
            leaf.leaf_id = subgoal_id
        if not leaf.goal:
            leaf.goal = title
        if not leaf.acceptance:
            leaf.acceptance = criteria
        if leaf.tick is None:
            leaf.tick = tick
        return leaf
    return LeafContract(
        leaf_id=subgoal_id,
        goal=title,
        acceptance=criteria,
        tick=tick,
    )

class MakerActor(Worker):
    pattern = f"{topics.ROLE_MAKER_RUN}.*"
    result_prefix = topics.ROLE_MAKER_RESULT
    error_code = "maker_failed"

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
            raise AssertionError("Maker MCP requires tools_allowed=True")
        self.adapter: AgentAdapter = adapter or MockAdapter()
        self.workdir = Path(workdir).resolve() if workdir else Path.cwd()
        self.tools_allowed = tools_allowed
        self.mcp_config = mcp_config
        self.add_dirs = tuple(add_dirs or ())

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        tick = int(args.get("tick", 0))
        subgoal_id = str(args.get("subgoal_id") or "root")
        criteria = [str(x) for x in (args.get("done_criteria") or ["done"])]
        title = str(args.get("goal_title") or args.get("title") or subgoal_id)
        workdir = Path(args.get("workdir") or self.workdir).resolve()
        tee_path = args.get("tee_path")
        leaf = _leaf_from_args(
            args, tick=tick, subgoal_id=subgoal_id, criteria=criteria, title=title
        )
        leaf_block = leaf.render_maker_block()
        obligation_refs = [
            str(x)
            for x in (
                args.get("obligation_refs")
                or (args.get("leaf_contract") or {}).get("obligation_refs")
                or []
            )
            if str(x).strip()
        ]
        contract_ref = str(args.get("contract_ref") or "")
        world_revision = args.get("world_revision")
        from eglk_harness.domain.runtime.contract_align import render_contract_binding_block

        binding_block = render_contract_binding_block(
            contract_ref,
            obligation_refs,
            world_revision=int(world_revision) if world_revision is not None else None,
        )
        if binding_block:
            leaf_block = f"{leaf_block}\n\n{binding_block}"
        prompt = render_prompt("maker", leaf_block=leaf_block, workdir=workdir)
        meta = {
            "tick": tick,
            "subgoal_id": subgoal_id,
            "done_criteria": criteria,
            "obligation_refs": obligation_refs or None,
            "contract_ref": contract_ref or None,
            "world_revision": int(world_revision) if world_revision is not None else None,
        }
        request = EpisodeRequest(
            role="maker",
            prompt=prompt,
            workdir=workdir,
            tools_allowed=self.tools_allowed,
            mcp_config=self.mcp_config if self.tools_allowed else None,
            add_dirs=self.add_dirs if self.tools_allowed else (),
            expect="claim",
            model=resolve_model("maker"),
            timeout_s=float(args.get("timeout_s") or 600.0),
            meta=meta,
            tee_path=str(tee_path) if tee_path else None,
        )
        result = await run_with_format_repair(
            self.adapter, request, leaf_block=leaf_block
        )
        if not result.ok or not isinstance(result.parsed, dict):
            messages.work_error(result.error or "maker_episode_failed")
        from eglk_harness.domain.kernel.schema_validate import coerce_document
        from eglk_harness.domain.runtime.contract_align import align_claim_to_contract

        claim = coerce_document("claim", dict(result.parsed))
        claim = align_claim_to_contract(
            claim,
            contract_ref=contract_ref,
            obligation_refs=obligation_refs,
            world_revision_base=int(world_revision) if world_revision is not None else None,
            node_id=subgoal_id,
        )
        if not str(claim.get("intent") or "").strip() or claim.get("intent") == "(unspecified)":
            claim["intent"] = title
        claim["tick"] = tick
        claim["subgoal_id"] = subgoal_id
        import uuid

        sid = str(claim.get("maker_session_id") or "").strip()
        if not sid or sid == "unknown":
            claim["maker_session_id"] = f"maker-{uuid.uuid4().hex[:12]}"
        return messages.ok_value(
            claim=claim,
            tokens=int(result.tokens or 0),
            cost_usd=float(result.cost_usd or 0.0),
            format_repair_tokens=int(result.format_repair_tokens or 0),
            format_repair_cost_usd=float(result.format_repair_cost_usd or 0.0),
        )
