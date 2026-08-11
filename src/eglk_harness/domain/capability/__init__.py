"""Capability Broker — default-deny role × resource × operation authorization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from eglk_harness.domain.kernel.projections import CAPABILITY_MANIFEST_SCHEMA

SIDE_EFFECT_RANK = {
    "read_only": 0,
    "reversible": 1,
    "compensatable": 2,
    "irreversible": 3,
}


@dataclass(frozen=True)
class CapabilityEntry:
    id: str
    role: str
    resource: str
    operation: str
    allowed_side_effect_classes: tuple[str, ...]
    requires_idempotency_key: bool = False

    def allows(self, side_effect_class: str) -> bool:
        return side_effect_class in self.allowed_side_effect_classes


@dataclass
class CapabilityManifest:
    schema: str
    manifest_id: str
    default_deny: bool
    entries: list[CapabilityEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "manifest_id": self.manifest_id,
            "default_deny": True,
            "entries": [
                {
                    "id": e.id,
                    "role": e.role,
                    "resource": e.resource,
                    "operation": e.operation,
                    "allowed_side_effect_classes": list(e.allowed_side_effect_classes),
                    "requires_idempotency_key": e.requires_idempotency_key,
                }
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CapabilityManifest:
        entries: list[CapabilityEntry] = []
        for raw in data.get("entries") or []:
            if not isinstance(raw, Mapping):
                continue
            entries.append(
                CapabilityEntry(
                    id=str(raw["id"]),
                    role=str(raw["role"]),
                    resource=str(raw["resource"]),
                    operation=str(raw["operation"]),
                    allowed_side_effect_classes=tuple(
                        str(x) for x in (raw.get("allowed_side_effect_classes") or [])
                    ),
                    requires_idempotency_key=bool(raw.get("requires_idempotency_key", False)),
                )
            )
        return cls(
            schema=str(data.get("schema") or CAPABILITY_MANIFEST_SCHEMA),
            manifest_id=str(data.get("manifest_id") or "default"),
            default_deny=True,
            entries=entries,
        )


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    reason: str
    entry_id: str | None = None


def _resource_match(pattern: str, resource: str) -> bool:
    """Simple glob: ``*`` matches any remaining suffix; exact otherwise."""
    if pattern == "*":
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return resource == prefix or resource.startswith(prefix.rstrip("/") + "/")
    if pattern.endswith("*"):
        return resource.startswith(pattern[:-1])
    return pattern == resource


class CapabilityBroker:
    """Default-deny broker. Holding a tool ≠ having capability."""

    def __init__(self, manifest: CapabilityManifest) -> None:
        if not manifest.default_deny:
            raise ValueError("CapabilityManifest.default_deny must be true")
        self.manifest = manifest

    def authorize(
        self,
        *,
        role: str,
        resource: str,
        operation: str,
        side_effect_class: str,
        idempotency_key: str | None = None,
    ) -> AuthDecision:
        role_l = role.strip().lower()
        matches = [
            e
            for e in self.manifest.entries
            if e.role == role_l
            and e.operation == operation
            and _resource_match(e.resource, resource)
        ]
        if not matches:
            return AuthDecision(False, "capability_denied_no_entry")
        # Prefer the most specific (longest) resource pattern
        matches.sort(key=lambda e: len(e.resource), reverse=True)
        entry = matches[0]
        if not entry.allows(side_effect_class):
            return AuthDecision(False, "capability_ceiling_exceeded", entry.id)
        if entry.requires_idempotency_key or side_effect_class == "irreversible":
            if not idempotency_key or not str(idempotency_key).strip():
                return AuthDecision(False, "idempotency_key_required", entry.id)
        return AuthDecision(True, "authorized", entry.id)

    def authorize_action(
        self,
        *,
        role: str,
        action: Mapping[str, Any],
        ceiling: Sequence[str] | None = None,
    ) -> AuthDecision:
        sec = str(action.get("side_effect_class") or "")
        if ceiling is not None and sec not in ceiling:
            return AuthDecision(False, "capability_ceiling_exceeded")
        return self.authorize(
            role=role,
            resource=str(action.get("target") or ""),
            operation=str(action.get("kind") or ""),
            side_effect_class=sec,
            idempotency_key=action.get("idempotency_key"),
        )


def load_manifest(path: Path) -> CapabilityManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CapabilityManifest.from_dict(data)


def default_local_fs_manifest(*, manifest_id: str = "local-fs-default") -> CapabilityManifest:
    """Conservative default: Maker may reverse-write repo/**; Checker read-only."""
    return CapabilityManifest(
        schema=CAPABILITY_MANIFEST_SCHEMA,
        manifest_id=manifest_id,
        default_deny=True,
        entries=[
            CapabilityEntry(
                id="maker-repo-write",
                role="maker",
                resource="repo/**",
                operation="file_write",
                allowed_side_effect_classes=("reversible",),
            ),
            CapabilityEntry(
                id="maker-repo-read",
                role="maker",
                resource="repo/**",
                operation="file_read",
                allowed_side_effect_classes=("read_only",),
            ),
            CapabilityEntry(
                id="checker-repo-read",
                role="checker",
                resource="repo/**",
                operation="file_read",
                allowed_side_effect_classes=("read_only",),
            ),
            CapabilityEntry(
                id="maker-workdir-write",
                role="maker",
                resource="workdir/**",
                operation="file_write",
                allowed_side_effect_classes=("reversible",),
            ),
            CapabilityEntry(
                id="maker-agent-runs-write",
                role="maker",
                resource="agent_runs/**",
                operation="file_write",
                allowed_side_effect_classes=("reversible",),
            ),
            CapabilityEntry(
                id="maker-mcp-invoke",
                role="maker",
                resource="mcp:*",
                operation="mcp_invoke",
                allowed_side_effect_classes=("reversible", "compensatable"),
            ),
            CapabilityEntry(
                id="checker-mcp-read",
                role="checker",
                resource="mcp:*",
                operation="mcp_invoke",
                allowed_side_effect_classes=("read_only",),
            ),
            CapabilityEntry(
                id="maker-path-ack",
                role="maker",
                resource="workdir/**",
                operation="path_ack",
                allowed_side_effect_classes=("read_only",),
            ),
            CapabilityEntry(
                id="maker-agent-runs-ack",
                role="maker",
                resource="agent_runs/**",
                operation="path_ack",
                allowed_side_effect_classes=("read_only",),
            ),
            CapabilityEntry(
                id="checker-workdir-read",
                role="checker",
                resource="workdir/**",
                operation="file_read",
                allowed_side_effect_classes=("read_only",),
            ),
        ],
    )


def ensure_manifest(path: Path) -> CapabilityManifest:
    path = Path(path)
    if path.is_file():
        return load_manifest(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    m = default_local_fs_manifest()
    path.write_text(json.dumps(m.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return m
