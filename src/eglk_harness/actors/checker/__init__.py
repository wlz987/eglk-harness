"""Checker role actor — Adapter episode → Evidence JSON (read-only intent)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Mapping

from eba import Worker

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest
from eglk_harness.domain.adapters.mock import MockAdapter
from eglk_harness.domain.kernel.leaf_contract import LeafContract, contract_from_dict
from eglk_harness.domain.kernel.schema_validate import coerce_document
from eglk_harness.domain.memory.skills import render_prompt
from eglk_harness.domain.runtime.contract_align import (
    align_evidence_to_contract,
    render_contract_binding_block,
)
from eglk_harness.domain.runtime.evidence_guard import normalize_evidence
from eglk_harness.domain.runtime.format_repair import run_with_format_repair
from eglk_harness.domain.runtime.mechanical_evidence import (
    checker_mechanical_enabled,
    has_intent_obligations,
    synthesize_mechanical_evidence,
)
from eglk_harness.domain.runtime.models import resolve_model
from eglk_harness.protocol import messages, payload, topics


def _leaf_from_args(
    args: Mapping[str, Any],
    *,
    tick: int,
    subgoal_id: str,
    criteria: list[str],
    title: str,
) -> LeafContract:
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


def _checker_use_tools() -> bool:
    """Checker MCP follows tool_policy + EGLK_CHECKER_TOOLS (single control surface)."""
    from eglk_harness.domain.adapters.tool_policy import resolve_role_tool_profile

    return resolve_role_tool_profile("checker").tools_allowed


class CheckerActor(Worker):
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

    def _finalize_evidence(
        self,
        evidence: dict[str, Any],
        *,
        claim: Mapping[str, Any],
        written: list[str],
        mutations: list[str],
        workdir: Path,
        boundary: list[str],
        contract_ref: str,
        obligation_refs: list[str],
        world_revision: int | None,
        tick: int,
        subgoal_id: str,
        tokens: int = 0,
        cost_usd: float = 0.0,
        format_repair_tokens: int = 0,
        format_repair_cost_usd: float = 0.0,
    ) -> dict[str, Any]:
        evidence = normalize_evidence(
            evidence,
            written=written,
            mutations=mutations,
            workdir=workdir,
            boundary=boundary,
        )
        evidence = coerce_document("evidence", evidence)
        evidence = align_evidence_to_contract(
            evidence,
            contract_ref=contract_ref,
            obligation_refs=obligation_refs,
            world_revision=world_revision,
        )
        evidence["tick"] = tick
        evidence["subgoal_id"] = subgoal_id
        maker_sid = str(claim.get("maker_session_id") or "")
        csid = str(evidence.get("checker_session_id") or "").strip()
        if not csid or csid == "unknown" or csid == maker_sid:
            evidence["checker_session_id"] = f"checker-{uuid.uuid4().hex[:12]}"
        if contract_ref and not evidence.get("contract_ref"):
            evidence["contract_ref"] = contract_ref
        return messages.ok_value(
            evidence=evidence,
            tokens=int(tokens or 0),
            cost_usd=float(cost_usd or 0.0),
            format_repair_tokens=int(format_repair_tokens or 0),
            format_repair_cost_usd=float(format_repair_cost_usd or 0.0),
            checker_mechanical=bool(
                evidence.get("note") == "mechanical_evidence_from_boundary"
            ),
        )

    async def work(self, envelope_payload: Any) -> Any:
        args = payload.get_args(envelope_payload if isinstance(envelope_payload, dict) else {})
        tick = int(args.get("tick", 0))
        claim = args.get("claim") if isinstance(args.get("claim"), dict) else {}
        subgoal_id = str(args.get("subgoal_id") or claim.get("subgoal_id") or "root")
        written = list(args.get("written") or [])
        criteria = [str(x) for x in (args.get("done_criteria") or ["done"])]
        title = str(args.get("goal_title") or args.get("title") or subgoal_id)
        workdir = Path(args.get("workdir") or self.workdir).resolve()
        tee_path = args.get("tee_path")

        leaf = _leaf_from_args(
            args, tick=tick, subgoal_id=subgoal_id, criteria=criteria, title=title
        )
        leaf_block = leaf.render_checker_block()
        contract_ref = str(args.get("contract_ref") or claim.get("contract_ref") or "")
        obligation_refs = [
            str(x)
            for x in (
                args.get("obligation_refs")
                or (args.get("leaf_contract") or {}).get("obligation_refs")
                or []
            )
            if str(x).strip()
        ]
        raw_vt = args.get("obligation_verification_types")
        obligation_verification_types: dict[str, str] | None = None
        if "obligation_verification_types" in args:
            obligation_verification_types = {}
            if isinstance(raw_vt, Mapping):
                for k, v in raw_vt.items():
                    if str(k).strip():
                        obligation_verification_types[str(k)] = str(v)
        world_revision = args.get("world_revision")
        binding_block = render_contract_binding_block(
            contract_ref,
            obligation_refs,
            world_revision=int(world_revision) if world_revision is not None else None,
        )
        if binding_block:
            leaf_block = f"{leaf_block}\n\n{binding_block}"

        wr = int(world_revision) if world_revision is not None else None
        use_tools = bool(self.tools_allowed) and _checker_use_tools()
        boundary = list(leaf.boundary or [])
        mutations = list(args.get("mutations") or [])

        force_llm = os.environ.get("EGLK_CHECKER_FORCE_LLM", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        intent_obligations = has_intent_obligations(
            obligation_refs, obligation_verification_types
        )

        if checker_mechanical_enabled() and not force_llm and not intent_obligations:
            mech = synthesize_mechanical_evidence(
                workdir=workdir,
                claim=claim,
                contract_ref=contract_ref,
                obligation_refs=obligation_refs,
                boundary=boundary,
                world_revision=wr,
                tick=tick,
                written=written,
                obligation_verification_types=obligation_verification_types,
            )
            if mech is not None:
                return self._finalize_evidence(
                    mech,
                    claim=claim,
                    written=written,
                    mutations=mutations,
                    workdir=workdir,
                    boundary=boundary,
                    contract_ref=contract_ref,
                    obligation_refs=obligation_refs,
                    world_revision=wr,
                    tick=tick,
                    subgoal_id=subgoal_id,
                )

        observe_note = ""
        obs = args.get("observation")
        if isinstance(obs, dict) and obs.get("world_revision") is not None:
            observe_note = (
                f"\nFrozen observe world_revision={obs.get('world_revision')} "
                f"files={len(obs.get('files') or [])} artifacts={len(obs.get('artifacts') or [])}.\n"
                "Bind Attestation.world_revision to this revision; fill observation narrative only — no ground-truth answers.\n"
            )
        extra = (
            f"Maker claim:\n```json\n{claim}\n```\n"
            f"Applied paths: {written}\n"
            "Inspect the workdir; do not modify files.\n"
            "Verify every MUST_EXIST / FORBIDDEN boundary line mechanically."
            f"{observe_note}"
        )
        prompt = render_prompt("checker", leaf_block=leaf_block, extra=extra, workdir=workdir)
        request = EpisodeRequest(
            role="checker",
            prompt=prompt,
            workdir=workdir,
            tools_allowed=use_tools,
            mcp_config=self.mcp_config if use_tools else None,
            add_dirs=self.add_dirs if use_tools else (),
            expect="evidence",
            model=resolve_model("checker"),
            timeout_s=float(args.get("timeout_s") or 600.0),
            meta={
                "tick": tick,
                "subgoal_id": subgoal_id,
                "written": written,
                "claim": claim,
                "done_criteria": criteria,
                "obligation_refs": obligation_refs or None,
                "contract_ref": contract_ref or None,
                "world_revision": wr,
            },
            tee_path=str(tee_path) if tee_path else None,
        )
        result = await run_with_format_repair(
            self.adapter,
            request,
            leaf_block=f"{leaf_block}\n\n{extra}",
        )
        if result.ok and isinstance(result.parsed, dict):
            return self._finalize_evidence(
                dict(result.parsed),
                claim=claim,
                written=written,
                mutations=mutations,
                workdir=workdir,
                boundary=boundary,
                contract_ref=contract_ref,
                obligation_refs=obligation_refs,
                world_revision=wr,
                tick=tick,
                subgoal_id=subgoal_id,
                tokens=int(result.tokens or 0),
                cost_usd=float(result.cost_usd or 0.0),
                format_repair_tokens=int(result.format_repair_tokens or 0),
                format_repair_cost_usd=float(result.format_repair_cost_usd or 0.0),
            )

        mech = synthesize_mechanical_evidence(
            workdir=workdir,
            claim=claim,
            contract_ref=contract_ref,
            obligation_refs=obligation_refs,
            boundary=boundary,
            world_revision=wr,
            tick=tick,
            written=written,
            obligation_verification_types=obligation_verification_types,
        )
        if mech is not None:
            return self._finalize_evidence(
                mech,
                claim=claim,
                written=written,
                mutations=mutations,
                workdir=workdir,
                boundary=boundary,
                contract_ref=contract_ref,
                obligation_refs=obligation_refs,
                world_revision=wr,
                tick=tick,
                subgoal_id=subgoal_id,
            )
        messages.work_error(result.error or "checker_episode_failed")
