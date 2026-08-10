"""Sanitize Maker ActionClaim actions before Capability Broker / world apply.

Work episode may use MCP/tools; Claim episode is tools-off attestation.
Narrative MCP steps must not be re-authorized or re-applied.
"""

from __future__ import annotations

from typing import Any, Mapping

# Already executed in Work episode — Claim may mention them for audit only.
_NARRATIVE_KINDS = frozenset(
    {
        "mcp_session",
        "mcp_invoke",
        "mcp_call",
        "browser",
        "tool_call",
        "ui_click",
        "ui_type",
        "navigate",
    }
)

# Acknowledge on-disk deliverables; no Capability Broker entry required.
_ACK_KINDS = frozenset({"path_ack", "mcp_delivery", "external_write"})


def _normalize_file_target(target: str) -> str:
    t = str(target or "").strip().lstrip("/").replace("\\", "/")
    if t.startswith("workdir/"):
        return t[len("workdir/") :]
    return t


def _broker_resource_for_file_write(target: str) -> str:
    """Map file_write targets onto CapabilityManifest resource patterns.

    Manifest entries use ``workdir/**`` / ``agent_runs/**`` / ``repo/**``.
    Bare relative paths (e.g. ``hello.txt``) authorize as ``workdir/hello.txt``.
    """
    t = _normalize_file_target(target)
    if not t:
        return t
    if t.startswith(("agent_runs/", "repo/", "workdir/")):
        return t
    return f"workdir/{t}"


def sanitize_claim_for_apply(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of claim whose ``actions`` are safe to authorize + apply.

    - Drops narrative MCP/browser kinds (Work episode already mutated the world).
    - Keeps ``file_write`` / ``path_ack`` / ``mcp_delivery`` for disk ack or write.
    - Normalizes ``file_write`` targets to workdir-relative paths for apply.
    """
    out = dict(claim)
    raw = list(out.get("actions") or [])
    kept: list[dict[str, Any]] = []
    for action in raw:
        if not isinstance(action, Mapping):
            continue
        kind = str(action.get("kind") or "").strip()
        if kind in _NARRATIVE_KINDS:
            continue
        item = dict(action)
        if kind == "file_write":
            target = _normalize_file_target(str(item.get("target") or ""))
            if target:
                item["target"] = target
            payload = item.get("payload")
            if isinstance(payload, Mapping):
                pl = dict(payload)
                if pl.get("path"):
                    pl["path"] = _normalize_file_target(str(pl["path"]))
                item["payload"] = pl
        kept.append(item)
    out["actions"] = kept
    return out


def actions_requiring_broker(actions: list[Mapping[str, Any]] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Subset of actions that must pass Capability Broker before apply."""
    out: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, Mapping):
            continue
        kind = str(action.get("kind") or "").strip()
        if kind in _ACK_KINDS or kind in _NARRATIVE_KINDS:
            continue
        if not kind:
            continue
        item = dict(action)
        if kind == "file_write":
            target = _broker_resource_for_file_write(str(item.get("target") or ""))
            if target:
                item["target"] = target
        out.append(item)
    return out
