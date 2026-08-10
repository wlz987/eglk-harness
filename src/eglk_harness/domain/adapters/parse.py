"""Parse Adapter stdout into EpisodeResult (shared by Codex / Claude)."""

from __future__ import annotations

from eglk_harness.domain.adapters.base import EpisodeRequest, EpisodeResult
from eglk_harness.domain.kernel.schema_validate import parse_and_validate


def episode_from_text(request: EpisodeRequest, text: str, *, backend: str) -> EpisodeResult:
    if request.expect == "text":
        return EpisodeResult(ok=True, text=text, backend=backend)
    schema = "claim" if request.expect == "claim" else "evidence"
    parsed, errs = parse_and_validate(schema, text)
    tokens = 0
    cost_usd = 0.0
    if backend == "codex" and text:
        from eglk_harness.domain.memory.tokens import tokens_from_codex_jsonl

        tokens = tokens_from_codex_jsonl(text)
    if errs or parsed is None:
        return EpisodeResult(
            ok=False,
            text=text,
            error="unparseable:" + ";".join(errs),
            backend=backend,
            tokens=tokens,
            cost_usd=cost_usd,
        )
    return EpisodeResult(ok=True, text=text, parsed=parsed, backend=backend, tokens=tokens, cost_usd=cost_usd)
