"""One-shot JSON schema format repair for Maker/Checker episodes (LH-shaped, eglk-owned)."""

from __future__ import annotations

from eglk_harness.domain.adapters.base import AgentAdapter, EpisodeRequest, EpisodeResult
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


async def run_with_format_repair(
    adapter: AgentAdapter,
    request: EpisodeRequest,
    *,
    leaf_block: str,
    enabled: bool = True,
) -> EpisodeResult:
    """Run episode; on unparseable claim/evidence, retry once with a repair prompt."""
    first = await adapter.run_episode(request)
    if request.expect == "text":
        return first
    if first.ok and isinstance(first.parsed, dict):
        return first
    if not enabled:
        return first
    err = first.error or "unparseable"
    repair_req = EpisodeRequest(
        role=request.role,
        prompt=repair_prompt(
            role=request.role,
            leaf_block=leaf_block,
            previous_error=err,
            previous_text=first.text or "",
        ),
        workdir=request.workdir,
        tools_allowed=request.tools_allowed,
        mcp_config=request.mcp_config,
        add_dirs=request.add_dirs,
        model=request.model,
        timeout_s=min(float(request.timeout_s), 300.0),
        expect=request.expect,
        meta={**dict(request.meta), "format_repair": True},
        tee_path=request.tee_path,
    )
    second = await adapter.run_episode(repair_req)
    if second.ok and isinstance(second.parsed, dict):
        second.tokens = int(first.tokens or 0) + int(second.tokens or 0)
        second.cost_usd = float(first.cost_usd or 0) + float(second.cost_usd or 0)
        return second
    # Prefer the more informative error
    if not second.error and first.error:
        second.error = first.error
    second.tokens = int(first.tokens or 0) + int(second.tokens or 0)
    second.cost_usd = float(first.cost_usd or 0) + float(second.cost_usd or 0)
    return second
