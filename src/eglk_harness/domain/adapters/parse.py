"""Parse Adapter stdout into EpisodeResult (shared by Codex / Claude)."""

from __future__ import annotations

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.json_extract import unwrap_agent_jsonl
from eglk_harness.domain.schema_validate import parse_and_validate
from eglk_harness.domain.tokens import tokens_from_codex_jsonl


def episode_from_text(request: EpisodeRequest, text: str, *, backend: str) -> EpisodeResult:
    body = unwrap_agent_jsonl(text)
    from eglk_harness.domain.metering import tokens_and_cost_from_raw

    metered_tokens, cost_usd = tokens_and_cost_from_raw(text)
    tokens = metered_tokens or (tokens_from_codex_jsonl(text) if backend == "codex" else 0)
    if request.expect == "text":
        return EpisodeResult(ok=True, text=body, tokens=tokens, cost_usd=cost_usd, backend=backend)
    schema = "claim" if request.expect == "claim" else "evidence"
    parsed, errs = parse_and_validate(schema, body)
    if errs or parsed is None:
        return EpisodeResult(
            ok=False,
            text=text,
            error="unparseable:" + ";".join(errs),
            tokens=tokens,
            cost_usd=cost_usd,
            backend=backend,
        )
    return EpisodeResult(
        ok=True, text=text, parsed=parsed, tokens=tokens, cost_usd=cost_usd, backend=backend
    )
