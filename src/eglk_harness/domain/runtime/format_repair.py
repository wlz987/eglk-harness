"""JSON schema format repair for Maker/Checker episodes (LH-shaped, eglk-owned)."""

from __future__ import annotations

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest, EpisodeResult
from eglk_harness.domain.kernel.schema_validate import try_parse_document
from eglk_harness.domain.memory.skills import render_prompt


def repair_prompt(*, role: str, leaf_block: str, previous_error: str, previous_text: str = "") -> str:
    """Build a no-tools-friendly repair prompt (still tools_allowed follows request)."""
    extra = (
        f"FORMAT REPAIR: previous output failed validation ({previous_error}).\n"
        "Return a single JSON object only that satisfies the schema.\n"
        "Do not wrap in markdown. Do not include prose outside JSON.\n"
    )
    if previous_text.strip():
        extra += f"\nPrevious output (truncated):\n```\n{previous_text[:2000]}\n```\n"
    return render_prompt(role, leaf_block=leaf_block, extra=extra)


def _schema_name(expect: str) -> str | None:
    if expect == "claim":
        return "claim"
    if expect == "evidence":
        return "evidence"
    return None


async def run_with_format_repair(
    adapter: AgentAdapter,
    request: EpisodeRequest,
    *,
    leaf_block: str,
    enabled: bool = True,
    max_repairs: int = 2,
) -> EpisodeResult:
    """Run episode; on unparseable claim/evidence, re-coerce then LLM-repair up to ``max_repairs``."""
    binding_hint = ""
    meta = request.meta or {}
    cref = str(meta.get("contract_ref") or "").strip()
    refs = [str(x) for x in (meta.get("obligation_refs") or []) if str(x).strip()]
    if cref or refs:
        from eglk_harness.domain.runtime.contract_align import render_contract_binding_block

        wr = meta.get("world_revision")
        binding_hint = render_contract_binding_block(
            cref,
            refs,
            world_revision=int(wr) if wr is not None else None,
        )
    if binding_hint:
        leaf_block = f"{leaf_block}\n\n{binding_hint}"
    first = await adapter.run_episode(request)
    primary_tokens = int(first.tokens or 0)
    primary_cost = float(first.cost_usd or 0.0)
    repair_tokens = 0
    repair_cost = 0.0
    if request.expect == "text":
        return first
    if first.ok and isinstance(first.parsed, dict):
        first.format_repair_tokens = 0
        first.format_repair_cost_usd = 0.0
        return first
    if not enabled or max_repairs <= 0:
        first.format_repair_tokens = 0
        first.format_repair_cost_usd = 0.0
        return first

    schema = _schema_name(request.expect)
    tokens = primary_tokens
    cost = primary_cost
    last = first
    previous_text = first.text or ""
    previous_error = first.error or "unparseable"

    # Deterministic recovery on the first raw text before spending another LLM call
    if schema and previous_text.strip():
        parsed, errs = try_parse_document(schema, previous_text)
        if parsed is not None and not errs:
            return EpisodeResult(
                ok=True,
                text=previous_text,
                parsed=parsed,
                tokens=tokens,
                cost_usd=cost,
                backend=first.backend,
                format_repair_tokens=repair_tokens,
                format_repair_cost_usd=repair_cost,
            )

    for attempt in range(max_repairs):
        repair_req = EpisodeRequest(
            role=request.role,
            prompt=repair_prompt(
                role=request.role,
                leaf_block=leaf_block,
                previous_error=previous_error,
                previous_text=previous_text,
            ),
            workdir=request.workdir,
            tools_allowed=False,
            mcp_config=None,
            add_dirs=(),
            model=request.model,
            timeout_s=min(float(request.timeout_s), 300.0),
            expect=request.expect,
            meta={**dict(request.meta), "format_repair": True, "format_repair_attempt": attempt + 1},
            tee_path=request.tee_path,
        )
        nxt = await adapter.run_episode(repair_req)
        repair_tokens += int(nxt.tokens or 0)
        repair_cost += float(nxt.cost_usd or 0.0)
        tokens = primary_tokens + repair_tokens
        cost = primary_cost + repair_cost
        nxt.tokens = tokens
        nxt.cost_usd = cost
        nxt.format_repair_tokens = repair_tokens
        nxt.format_repair_cost_usd = repair_cost
        if nxt.ok and isinstance(nxt.parsed, dict):
            return nxt
        if schema and (nxt.text or "").strip():
            parsed, errs = try_parse_document(schema, nxt.text)
            if parsed is not None and not errs:
                return EpisodeResult(
                    ok=True,
                    text=nxt.text,
                    parsed=parsed,
                    tokens=tokens,
                    cost_usd=cost,
                    backend=nxt.backend or first.backend,
                    format_repair_tokens=repair_tokens,
                    format_repair_cost_usd=repair_cost,
                )
        if not nxt.error and previous_error:
            nxt.error = previous_error
        last = nxt
        previous_text = nxt.text or previous_text
        previous_error = nxt.error or previous_error

    last.format_repair_tokens = repair_tokens
    last.format_repair_cost_usd = repair_cost
    return last
