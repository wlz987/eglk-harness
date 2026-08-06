"""Redact credentials before logs / EpisodeResult surfaces (LH-shaped)."""

from __future__ import annotations

import re

_SECRET_NAME = r"(?:API[_-]?KEY|AUTH[_-]?TOKEN|ACCESS[_-]?TOKEN|SECRET|PASSWORD|TOKEN|EGLK_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|CODEX_API_KEY)"
_SECRET_VALUE = r"(?:'[^']*'|\"[^\"]*\"|\S+)"
_SECRET_PATTERNS = (
    re.compile(rf"\b([A-Za-z0-9_]*{_SECRET_NAME}\s*=){_SECRET_VALUE}", re.I),
    re.compile(rf"(--[A-Za-z0-9-]*{_SECRET_NAME}[= ]){_SECRET_VALUE}", re.I),
    re.compile(rf'(["\']?(?:api[_-]?key|token|password|secret)["\']?\s*:\s*)(["\'][^"\']+["\'])', re.I),
)


def redact_secrets(text: str) -> str:
    """Mask credential values in text before it is logged or shown to a role."""
    if not text:
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(r"\1***REDACTED***", out)
    return out
