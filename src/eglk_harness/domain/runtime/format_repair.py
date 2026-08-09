"""JSON schema format repair for Maker/Checker episodes (LH-shaped, eglk-owned)."""

from __future__ import annotations

from pathlib import Path

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest, EpisodeResult
from eglk_harness.domain.kernel.schema_validate import try_parse_document
from eglk_harness.domain.memory.skills import render_prompt


def repair_prompt(
    *,
    role: str,
    leaf_block: str,
    previous_error: str,
    previous_text: str = "",
    workdir: Path | None = None,
    failure_kind: str | None = None,
) -> str:
    """Build a no-tools repair prompt — emit schema JSON only; do not re-mutate the world."""
    extra = (
        f"FORMAT REPAIR: previous output failed validation ({previous_error}).\n"
        "Return a single JSON object only that satisfies the schema.\n"
        "Do not wrap in markdown. Do not include prose outside JSON.\n"
        "Do **not** re-run tools, shell, or long benches — world artifacts already exist; "
        "only emit the missing Claim/Evidence JSON as your final assistant message.\n"
    )
    from eglk_harness.domain.runtime.episode_failure import failure_repair_extra

    kind_extra = failure_repair_extra(failure_kind)
    if kind_extra:
        extra += kind_extra + "\n"
    if previous_text.strip():
        extra += f"\nPrevious output (truncated):\n```\n{previous_text[:2000]}\n```\n"
    return render_prompt(
        role,
        leaf_block=leaf_block,
        extra=extra,
        workdir=workdir,
        format_repair=True,
    )


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
    workdir: Path | None = None,
    enabled: bool = True,
    max_repairs: int = 2,
) -> EpisodeResult:
    """Run episode; on unparseable claim/evidence, re-coerce then LLM-repair up to ``max_repairs``."""
    first = await adapter.run_episode(request)
    if request.expect == "text":
        return first
    if first.ok and isinstance(first.parsed, dict):
        return first
    if not enabled or max_repairs <= 0:
        return first

    schema = _schema_name(request.expect)
    tokens = int(first.tokens or 0)
    cost = float(first.cost_usd or 0.0)
    last = first
    previous_text = first.text or ""
    previous_error = first.error or "unparseable"
    from eglk_harness.domain.runtime.episode_failure import failure_kind_from_raw

    failure_kind = failure_kind_from_raw(previous_text)

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
            )

    for attempt in range(max_repairs):
        repair_req = EpisodeRequest(
            role=request.role,
            prompt=            repair_prompt(
                role=request.role,
                leaf_block=leaf_block,
                previous_error=previous_error,
                previous_text=previous_text,
                workdir=workdir or request.workdir,
                failure_kind=failure_kind,
            ),
            workdir=request.workdir,
            # Repair is JSON-only — never re-open tools/MCP (avoids re-running 30min benches).
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
        tokens += int(nxt.tokens or 0)
        cost += float(nxt.cost_usd or 0.0)
        nxt.tokens = tokens
        nxt.cost_usd = cost
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
                )
        if not nxt.error and previous_error:
            nxt.error = previous_error
        last = nxt
        previous_text = nxt.text or previous_text
        previous_error = nxt.error or previous_error

    return last
