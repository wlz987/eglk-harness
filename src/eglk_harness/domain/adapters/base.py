"""AgentAdapter protocol and episode types (LH-shaped; eglk control stays outside)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

# Roles allowed to receive MCP / tool surface (multi_agent.md §8).
TOOL_ROLES: frozenset[str] = frozenset({"maker", "checker"})

RoleName = Literal[
    "maker",
    "checker",
    "governor",
    "explorer",
    "verifier",
    "pruner",
    "refiner",
    "compile",
]


@dataclass(frozen=True)
class EpisodeRequest:
    """One Adapter session for a single role invocation."""

    role: str
    prompt: str
    workdir: Path
    tools_allowed: bool = False
    mcp_config: Path | None = None
    add_dirs: tuple[str, ...] = ()
    model: str | None = None
    timeout_s: float = 600.0
    expect: Literal["claim", "evidence", "text"] = "text"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Frozen dataclass: validate after init
        if self.tools_allowed and self.role not in TOOL_ROLES:
            raise AssertionError(
                f"tools_allowed=True illegal for role={self.role!r}; "
                f"only {sorted(TOOL_ROLES)} may hold MCP/tools"
            )
        if not self.tools_allowed and (self.mcp_config is not None or self.add_dirs):
            raise AssertionError(
                f"MCP/add_dirs supplied for role={self.role!r} with tools_allowed=False"
            )


@dataclass
class EpisodeResult:
    ok: bool
    text: str = ""
    parsed: dict[str, Any] | None = None
    error: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text,
            "parsed": self.parsed,
            "error": self.error,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "backend": self.backend,
        }


@runtime_checkable
class AgentAdapter(Protocol):
    """Backend envelope: preserves native tool loop; no Gate/admit authority."""

    name: str

    async def run_episode(self, request: EpisodeRequest) -> EpisodeResult: ...
