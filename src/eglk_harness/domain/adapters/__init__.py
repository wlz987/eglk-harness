"""Agent backends (Codex / Claude / Mock) — no bus/actor imports."""

from eglk_harness.domain.adapters.base import (
    SESSION_ROLES,
    TOOL_ROLES,
    AgentAdapter,
    EpisodeRequest,
    EpisodeResult,
)
from eglk_harness.domain.adapters.factory import adapter_names, create_adapter
from eglk_harness.domain.adapters.mock import MockAdapter

__all__ = [
    "SESSION_ROLES",
    "TOOL_ROLES",
    "AgentAdapter",
    "EpisodeRequest",
    "EpisodeResult",
    "MockAdapter",
    "adapter_names",
    "create_adapter",
]
