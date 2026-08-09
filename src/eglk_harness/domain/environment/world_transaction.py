"""WorldTransaction lifecycle — EnvironmentAdapter side-effect protocol."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from eglk_harness.domain.kernel.projections import WORLD_TRANSACTION_SCHEMA
from eglk_harness.domain.kernel.worldref import (
    WorldRef,
    apply_claim_payload,
    restore,
    snapshot_workdir,
)

SIDE_EFFECT_CLASSES = frozenset({"read_only", "reversible", "compensatable", "irreversible"})


@dataclass
class WorldTransaction:
    schema: str
    transaction_id: str
    node_id: str
    base_revision: int
    candidate_revision: int | None
    side_effect_class: str
    action_intents: list[str]
    status: str
    idempotency_keys: list[str] = field(default_factory=list)
    compensation_ref: str | None = None
    snapshot: Path | None = None
    touches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "transaction_id": self.transaction_id,
            "node_id": self.node_id,
            "base_revision": self.base_revision,
            "candidate_revision": self.candidate_revision,
            "side_effect_class": self.side_effect_class,
            "action_intents": list(self.action_intents),
            "status": self.status,
            "idempotency_keys": list(self.idempotency_keys),
            "compensation_ref": self.compensation_ref,
        }


@runtime_checkable
class EnvironmentAdapter(Protocol):
    def begin(self, *, node_id: str, base_revision: int, side_effect_class: str) -> WorldTransaction: ...

    def prepare(self, tx: WorldTransaction, actions: list[Mapping[str, Any]]) -> WorldTransaction: ...

    def apply(self, tx: WorldTransaction, *, claim_payload: Mapping[str, Any] | None) -> WorldTransaction: ...

    def observe_revision(self, tx: WorldTransaction) -> int: ...

    def observe(self, tx: WorldTransaction) -> dict[str, Any]: ...

    def commit(self, tx: WorldTransaction) -> WorldTransaction: ...

    def rollback(self, tx: WorldTransaction, workdir: Path) -> WorldTransaction: ...

    def compensate(self, tx: WorldTransaction) -> WorldTransaction: ...


@dataclass
class ObservationBundle:
    """Read-only observation at a frozen candidate_revision (Checker input material)."""

    world_revision: int
    side_effect_class: str
    files: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_revision": self.world_revision,
            "side_effect_class": self.side_effect_class,
            "files": list(self.files),
            "artifacts": list(self.artifacts),
            "notes": list(self.notes),
        }


class LocalFilesystemAdapter:
    """Reversible filesystem adapter using WorldRef snapshots (legacy-compatible)."""

    def __init__(self, workdir: Path, world_dir: Path) -> None:
        self.workdir = Path(workdir).resolve()
        self.world_dir = Path(world_dir).resolve()
        self.world_dir.mkdir(parents=True, exist_ok=True)
        self._idempo: dict[str, dict[str, Any]] = {}
        self._ledger_path = self.world_dir / "idempotency.json"
        if self._ledger_path.is_file():
            try:
                self._idempo = json.loads(self._ledger_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._idempo = {}

    def _save_idempo(self) -> None:
        self._ledger_path.write_text(
            json.dumps(self._idempo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def begin(self, *, node_id: str, base_revision: int, side_effect_class: str) -> WorldTransaction:
        if side_effect_class not in SIDE_EFFECT_CLASSES:
            raise ValueError(f"invalid side_effect_class: {side_effect_class}")
        return WorldTransaction(
            schema=WORLD_TRANSACTION_SCHEMA,
            transaction_id=f"tx-{uuid.uuid4().hex[:12]}",
            node_id=node_id,
            base_revision=base_revision,
            candidate_revision=None,
            side_effect_class=side_effect_class,
            action_intents=[],
            status="prepared",
        )

    def prepare(self, tx: WorldTransaction, actions: list[Mapping[str, Any]]) -> WorldTransaction:
        keys: list[str] = []
        for a in actions:
            tx.action_intents.append(str(a.get("action_id") or ""))
            key = a.get("idempotency_key")
            if key:
                keys.append(str(key))
                if str(key) in self._idempo:
                    # already applied — prepare succeeds but apply will no-op
                    pass
            if tx.side_effect_class == "irreversible" and not key:
                raise ValueError("irreversible action requires idempotency_key")
        tx.idempotency_keys = keys
        tx.status = "prepared"
        if tx.side_effect_class in {"reversible", "compensatable", "irreversible"}:
            snap = self.world_dir / f"pre_{tx.transaction_id}"
            ref = snapshot_workdir(
                self.workdir,
                snap,
                revision=tx.base_revision,
                tick=0,
                meta={"transaction_id": tx.transaction_id},
            )
            tx.snapshot = ref.snapshot
        return tx

    def apply(self, tx: WorldTransaction, *, claim_payload: Mapping[str, Any] | None) -> WorldTransaction:
        if tx.side_effect_class == "read_only":
            tx.status = "applied"
            tx.candidate_revision = tx.base_revision
            return tx
        # idempotent short-circuit
        for key in tx.idempotency_keys:
            if key in self._idempo:
                tx.status = "applied"
                tx.candidate_revision = int(self._idempo[key].get("candidate_revision", tx.base_revision + 1))
                tx.touches = list(self._idempo[key].get("touches") or [])
                return tx
        written = apply_claim_payload(self.workdir, claim_payload)
        tx.touches = list(written)
        tx.candidate_revision = tx.base_revision + 1
        tx.status = "applied"
        for key in tx.idempotency_keys:
            self._idempo[key] = {
                "transaction_id": tx.transaction_id,
                "candidate_revision": tx.candidate_revision,
                "touches": tx.touches,
            }
        self._save_idempo()
        return tx

    def observe_revision(self, tx: WorldTransaction) -> int:
        tx.status = "observed"
        return int(tx.candidate_revision if tx.candidate_revision is not None else tx.base_revision)

    def observe(self, tx: WorldTransaction) -> dict[str, Any]:
        """Unified read-only observe at frozen candidate_revision (no world writes)."""
        rev = self.observe_revision(tx)
        files: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        notes: list[str] = []
        # Touches from this transaction (relative paths)
        for rel in tx.touches:
            p = self.workdir / rel
            entry = {"path": rel, "exists": p.is_file(), "kind": "file"}
            if p.is_file():
                entry["size"] = p.stat().st_size
                entry["sha256"] = __import__("hashlib").sha256(p.read_bytes()).hexdigest()
            files.append(entry)
        # Common delivery / HAR artifacts (read-only listing)
        for pattern in ("agent_runs/**/agent_response.json", "agent_runs/**/network.har"):
            for hit in sorted(self.workdir.glob(pattern)):
                if not hit.is_file():
                    continue
                try:
                    rel = str(hit.relative_to(self.workdir)).replace("\\", "/")
                except ValueError:
                    continue
                artifacts.append(
                    {
                        "path": rel,
                        "kind": "har" if rel.endswith(".har") else "agent_response",
                        "size": hit.stat().st_size,
                        "sha256": __import__("hashlib").sha256(hit.read_bytes()).hexdigest(),
                    }
                )
        notes.append("observe is read_only; Checker must not apply")
        return ObservationBundle(
            world_revision=rev,
            side_effect_class="read_only",
            files=files,
            artifacts=artifacts,
            notes=notes,
        ).to_dict()

    def commit(self, tx: WorldTransaction) -> WorldTransaction:
        tx.status = "committed"
        return tx

    def rollback(self, tx: WorldTransaction, workdir: Path) -> WorldTransaction:
        if tx.side_effect_class != "reversible":
            raise ValueError("rollback only valid for reversible")
        if tx.snapshot is None:
            raise ValueError("missing snapshot for rollback")
        ref = WorldRef(snapshot=tx.snapshot, revision=tx.base_revision, meta={})
        restore(ref, workdir)
        tx.status = "rolled_back"
        tx.candidate_revision = tx.base_revision
        return tx

    def compensate(self, tx: WorldTransaction) -> WorldTransaction:
        if tx.side_effect_class != "compensatable":
            raise ValueError("compensate only valid for compensatable")
        # Best-effort: restore snapshot if available, else mark compensated without physical undo
        if tx.snapshot is not None:
            ref = WorldRef(snapshot=tx.snapshot, revision=tx.base_revision, meta={})
            restore(ref, self.workdir)
        tx.compensation_ref = f"comp-{tx.transaction_id}"
        tx.status = "compensated"
        return tx


def ceiling_class(actions: list[Mapping[str, Any]]) -> str:
    """Highest side_effect_class among actions (for transaction envelope)."""
    rank = {"read_only": 0, "reversible": 1, "compensatable": 2, "irreversible": 3}
    best = "read_only"
    for a in actions:
        sec = str(a.get("side_effect_class") or "read_only")
        if rank.get(sec, 0) > rank[best]:
            best = sec
    return best
