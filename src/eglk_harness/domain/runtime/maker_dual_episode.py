"""Maker dual episode: tools-on work pass, then tools-off Claim pass (design C)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest, EpisodeResult
from eglk_harness.domain.memory.episode import load_episode_extra
from eglk_harness.domain.memory.skills import render_prompt
from eglk_harness.domain.runtime.episode_failure import failure_kind_from_raw, failure_repair_extra
from eglk_harness.domain.runtime.claim_recovery import recover_claim_from_episode
from eglk_harness.domain.runtime.format_repair import run_with_format_repair
from eglk_harness.domain.runtime.mechanical_claim import (
    list_satisfied_must_exist,
    prefer_disk_bound_claim,
    synthesize_mechanical_claim,
)
from eglk_harness.domain.runtime.boundary_verify import parse_boundary_rules, promote_staged_deliverables, verify_boundary

def maker_dual_episode_enabled(tools_allowed: bool) -> bool:
    if not tools_allowed:
        return False
    raw = os.environ.get("EGLK_MAKER_DUAL_EPISODE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def mechanical_claim_first_enabled() -> bool:
    """When MUST_EXIST is met, prefer mechanical path_ack before claim LLM (design default on)."""
    raw = os.environ.get("EGLK_MAKER_MECHANICAL_FIRST", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _tee_variant(base: str | None, suffix: str) -> str | None:
    if not base:
        return None
    p = Path(base)
    if p.suffix == ".jsonl":
        stem = p.name[: -len(".jsonl")]
        return str(p.with_name(f"{stem}{suffix}.jsonl"))
    return str(p.parent / f"{p.name}{suffix}.jsonl")


def _artifact_block(workdir: Path, boundary: Sequence[str]) -> str:
    promote_staged_deliverables(workdir, boundary)
    rules = parse_boundary_rules(boundary)
    lines: list[str] = ["[ON_DISK_ARTIFACTS]"]
    for rel, note in rules.must_exist:
        path = workdir / rel
        status = "present" if path.is_file() else "missing"
        extra = f" ({note})" if note else ""
        lines.append(f"- {rel}: {status}{extra}")
    satisfied = list_satisfied_must_exist(workdir, boundary)
    if satisfied:
        lines.append("boundary_ok: true")
        lines.append("satisfied_paths: " + ", ".join(satisfied))
    else:
        violations = verify_boundary(workdir, boundary)
        if violations:
            lines.append("boundary_ok: false")
            for v in violations[:8]:
                lines.append(f"- gap: {v}")
    return "\n".join(lines)


def _merge_tokens(primary: EpisodeResult, secondary: EpisodeResult) -> EpisodeResult:
    tokens = int(primary.tokens or 0) + int(secondary.tokens or 0)
    cost = float(primary.cost_usd or 0) + float(secondary.cost_usd or 0)
    fr_tokens = int(primary.format_repair_tokens or 0) + int(secondary.format_repair_tokens or 0)
    fr_cost = float(primary.format_repair_cost_usd or 0) + float(secondary.format_repair_cost_usd or 0)
    secondary.tokens = tokens
    secondary.cost_usd = cost
    secondary.format_repair_tokens = fr_tokens
    secondary.format_repair_cost_usd = fr_cost
    return secondary


def _disk_bound_claim(
    claim: dict[str, Any] | None,
    *,
    workdir: Path,
    boundary: Sequence[str],
    title: str,
    subgoal_id: str,
    contract_ref: str,
    world_revision: int | None,
    obligation_refs: Sequence[str],
    tick: int,
    maker_session_id: str | None = None,
) -> dict[str, Any] | None:
    return prefer_disk_bound_claim(
        claim,
        workdir=workdir,
        boundary=boundary,
        title=title,
        subgoal_id=subgoal_id,
        contract_ref=contract_ref,
        world_revision=world_revision,
        obligation_refs=obligation_refs,
        tick=tick,
        maker_session_id=maker_session_id,
    )


async def run_maker_dual_episode(
    adapter: AgentAdapter,
    *,
    workdir: Path,
    leaf_block: str,
    boundary: Sequence[str],
    title: str,
    subgoal_id: str,
    tick: int,
    contract_ref: str,
    obligation_refs: Sequence[str],
    world_revision: int | None,
    tools_allowed: bool,
    mcp_config: Path | None,
    add_dirs: tuple[str, ...],
    model: str | None,
    timeout_s: float,
    tee_path: str | None,
    meta: Mapping[str, Any],
) -> EpisodeResult:
    """Episode 1: tools work. Episode 2: tools-off Claim (+ mechanical fallback)."""
    workdir = workdir.resolve()
    work_timeout = min(timeout_s, float(os.environ.get("EGLK_MAKER_WORK_TIMEOUT_S", "1200") or 1200))
    claim_timeout = min(timeout_s, float(os.environ.get("EGLK_MAKER_CLAIM_TIMEOUT_S", "180") or 180))

    work_prompt = render_prompt(
        "maker",
        leaf_block=leaf_block,
        extra=load_episode_extra("maker_work", workdir),
        workdir=workdir,
    )
    work_req = EpisodeRequest(
        role="maker",
        prompt=work_prompt,
        workdir=workdir,
        tools_allowed=True,
        mcp_config=mcp_config,
        add_dirs=add_dirs,
        expect="text",
        model=model,
        timeout_s=work_timeout,
        meta={**dict(meta), "maker_episode": "work"},
        tee_path=_tee_variant(tee_path, "_work"),
    )
    work_result = await adapter.run_episode(work_req)
    if work_result.text:
        from eglk_harness.domain.adapters.agent_logs import write_trajectory_sidecars

        write_trajectory_sidecars(work_req.tee_path, work_result.text)

    if mechanical_claim_first_enabled():
        mech = synthesize_mechanical_claim(
            workdir=workdir,
            title=title,
            subgoal_id=subgoal_id,
            contract_ref=contract_ref,
            world_revision=world_revision,
            obligation_refs=obligation_refs,
            boundary=boundary,
            tick=tick,
        )
        if mech is not None:
            mech_result = EpisodeResult(
                ok=True,
                parsed=mech,
                text="mechanical_claim_from_boundary",
                backend="mechanical",
            )
            return _merge_tokens(work_result, mech_result)

    artifact_block = _artifact_block(workdir, boundary)
    claim_extra = f"{load_episode_extra('maker_claim', workdir)}\n\n{artifact_block}"
    if work_result.text and work_result.text.strip():
        claim_extra += f"\n\n[WORK_EPISODE_SUMMARY]\n{work_result.text[:4000]}"
    if not work_result.ok and work_result.error:
        claim_extra += f"\n\n[WORK_EPISODE_NOTE] prior episode ended: {work_result.error}"

    claim_leaf = f"{leaf_block}\n\n{artifact_block}"
    claim_prompt = render_prompt(
        "maker",
        leaf_block=claim_leaf,
        extra=claim_extra,
        workdir=workdir,
    )
    claim_meta = {
        **dict(meta),
        "maker_episode": "claim",
        "work_episode_ok": work_result.ok,
        "work_episode_error": work_result.error,
    }
    claim_req = EpisodeRequest(
        role="maker",
        prompt=claim_prompt,
        workdir=workdir,
        tools_allowed=False,
        mcp_config=None,
        add_dirs=(),
        expect="claim",
        model=model,
        timeout_s=claim_timeout,
        meta=claim_meta,
        tee_path=_tee_variant(tee_path, "_claim"),
    )
    claim_result = await run_with_format_repair(
        adapter,
        claim_req,
        leaf_block=claim_leaf,
        max_repairs=int(os.environ.get("EGLK_MAKER_CLAIM_FORMAT_REPAIRS", "1") or 1),
    )
    if claim_result.text:
        from eglk_harness.domain.adapters.agent_logs import write_trajectory_sidecars

        write_trajectory_sidecars(claim_req.tee_path, claim_result.text)

    if claim_result.ok and isinstance(claim_result.parsed, dict):
        bound = _disk_bound_claim(
            dict(claim_result.parsed),
            workdir=workdir,
            boundary=boundary,
            title=title,
            subgoal_id=subgoal_id,
            contract_ref=contract_ref,
            world_revision=world_revision,
            obligation_refs=obligation_refs,
            tick=tick,
            maker_session_id=str(claim_result.parsed.get("maker_session_id") or ""),
        )
        if bound is not None:
            claim_result.parsed = bound
        return _merge_tokens(work_result, claim_result)

    recovered = recover_claim_from_episode(claim_req.tee_path, claim_result.text)
    if recovered is not None:
        bound = _disk_bound_claim(
            recovered,
            workdir=workdir,
            boundary=boundary,
            title=title,
            subgoal_id=subgoal_id,
            contract_ref=contract_ref,
            world_revision=world_revision,
            obligation_refs=obligation_refs,
            tick=tick,
            maker_session_id=str(recovered.get("maker_session_id") or ""),
        )
        merged = _merge_tokens(work_result, claim_result)
        merged.ok = True
        merged.parsed = bound if bound is not None else recovered
        merged.error = None
        if not merged.text:
            merged.text = "claim_recovered_from_episode_artifacts"
        return merged

    # Mechanical fallback when boundary satisfied (no Oracle)
    mech = synthesize_mechanical_claim(
        workdir=workdir,
        title=title,
        subgoal_id=subgoal_id,
        contract_ref=contract_ref,
        world_revision=world_revision,
        obligation_refs=obligation_refs,
        boundary=boundary,
        tick=tick,
    )
    if mech is not None:
        merged = _merge_tokens(work_result, claim_result)
        merged.ok = True
        merged.parsed = mech
        merged.error = None
        if not merged.text:
            merged.text = "mechanical_claim_from_boundary"
        return merged

    # Enrich repair hint for a follow-up format repair attempt on failure text
    kind = failure_kind_from_raw(claim_result.text or work_result.text or "")
    extra = failure_repair_extra(kind)
    if extra and claim_result.error:
        claim_result.error = f"{claim_result.error}; {extra[:200]}"

    merged = _merge_tokens(work_result, claim_result)
    merged.ok = False
    merged.error = claim_result.error or work_result.error or "maker_claim_episode_failed"
    return merged
