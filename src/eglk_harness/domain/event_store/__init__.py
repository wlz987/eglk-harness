"""Append-only EventStore (SQLite WAL) — sole runtime authority."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from eglk_harness.domain.kernel.projections import EVENT_SCHEMA

_EVENT_TYPES = frozenset(
    {
        "RunCreated",
        "GoalCompiled",
        "ObligationOpened",
        "ObligationAmendmentProposed",
        "ObligationAmended",
        "ObligationAmendmentRejected",
        "SplitProposed",
        "SplitCommitted",
        "MergeProposed",
        "MergeCommitted",
        "NodeReady",
        "ContractAssembled",
        "TransactionPrepared",
        "ActionDispatched",
        "TransactionObserved",
        "EvidenceRecorded",
        "GateDecided",
        "ObligationSatisfied",
        "ObligationInvalidated",
        "TransactionCommitted",
        "TransactionRolledBack",
        "TransactionCompensated",
        "QuotaUpdated",
        "MemoryCandidateWritten",
        "MemoryPromoted",
        "MemoryDeprecated",
        "CapabilityDenied",
        "RunSucceeded",
        "RunAborted",
        "RunInvalid",
        "RunFaulted",
        "RunRecoveryStarted",
        "RunRecoveryCompleted",
        "CommandRejected",
    }
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def payload_digest(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_hex(canonical)


def event_hash(*, prev_hash: str | None, sequence: int, type_: str, payload_digest_s: str) -> str:
    prev = prev_hash or ""
    material = f"{prev}|{sequence}|{type_}|{payload_digest_s}"
    return _sha256_hex(material)


@dataclass(frozen=True)
class EventEnvelope:
    schema: str
    event_id: str
    sequence: int
    prev_hash: str | None
    hash: str
    type: str
    occurred_at: str
    payload: dict[str, Any]
    actor: str | None = None
    payload_digest: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": self.schema,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "type": self.type,
            "occurred_at": self.occurred_at,
            "payload": dict(self.payload),
        }
        if self.actor is not None:
            out["actor"] = self.actor
        if self.payload_digest is not None:
            out["payload_digest"] = self.payload_digest
        if self.causation_id is not None:
            out["causation_id"] = self.causation_id
        if self.correlation_id is not None:
            out["correlation_id"] = self.correlation_id
        return out

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> EventEnvelope:
        data = dict(row) if not isinstance(row, dict) else row
        payload = data["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(
            schema=str(data.get("schema") or EVENT_SCHEMA),
            event_id=str(data["event_id"]),
            sequence=int(data["sequence"]),
            prev_hash=data.get("prev_hash"),
            hash=str(data["hash"]),
            type=str(data["type"]),
            occurred_at=str(data["occurred_at"]),
            payload=dict(payload or {}),
            actor=data.get("actor"),
            payload_digest=data.get("payload_digest"),
            causation_id=data.get("causation_id"),
            correlation_id=data.get("correlation_id"),
        )


class EventStoreError(RuntimeError):
    """Base error for EventStore operations."""


class HashChainBroken(EventStoreError):
    pass


class WriteContention(EventStoreError):
    pass


class WriteLeaseError(EventStoreError):
    pass


class EventStore:
    """SQLite-WAL append-only event log. Sole writer path for runtime state."""

    def __init__(self, db_path: Path, *, lease_path: Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.lease_path = Path(lease_path) if lease_path else self.db_path.parent / ".write_lease"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              sequence INTEGER PRIMARY KEY,
              event_id TEXT NOT NULL UNIQUE,
              schema TEXT NOT NULL,
              prev_hash TEXT,
              hash TEXT NOT NULL,
              type TEXT NOT NULL,
              occurred_at TEXT NOT NULL,
              actor TEXT,
              payload TEXT NOT NULL,
              payload_digest TEXT,
              causation_id TEXT,
              correlation_id TEXT
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")

    def acquire_lease(self, *, holder: str, ttl_s: float = 120.0) -> None:
        """Acquire exclusive write lease (pid/holder + ttl)."""
        now = time.time()
        if self.lease_path.is_file():
            try:
                data = json.loads(self.lease_path.read_text(encoding="utf-8"))
                exp = float(data.get("expires_at", 0))
                if exp > now and str(data.get("holder")) != holder:
                    raise WriteLeaseError(f"lease held by {data.get('holder')}")
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass
        payload = {
            "holder": holder,
            "acquired_at": now,
            "expires_at": now + ttl_s,
            "pid": holder,
        }
        self.lease_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def release_lease(self, *, holder: str) -> None:
        if not self.lease_path.is_file():
            return
        try:
            data = json.loads(self.lease_path.read_text(encoding="utf-8"))
            if str(data.get("holder")) != holder:
                return
        except (json.JSONDecodeError, OSError):
            return
        self.lease_path.unlink(missing_ok=True)

    def tail(self) -> EventEnvelope | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        return EventEnvelope.from_row(row) if row else None

    def next_sequence(self) -> int:
        t = self.tail()
        return 0 if t is None else t.sequence + 1

    def read_all(self) -> list[EventEnvelope]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM events ORDER BY sequence ASC").fetchall()
        return [EventEnvelope.from_row(r) for r in rows]

    def read_from(self, sequence: int) -> list[EventEnvelope]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE sequence >= ? ORDER BY sequence ASC",
                (int(sequence),),
            ).fetchall()
        return [EventEnvelope.from_row(r) for r in rows]

    def verify_hash_chain(self) -> None:
        events = self.read_all()
        prev: str | None = None
        for ev in events:
            if ev.sequence == 0 and ev.prev_hash is not None:
                raise HashChainBroken(f"seq0 prev_hash must be null, got {ev.prev_hash}")
            if ev.sequence > 0 and ev.prev_hash != prev:
                raise HashChainBroken(
                    f"seq={ev.sequence} prev_hash mismatch: want {prev} got {ev.prev_hash}"
                )
            pd = ev.payload_digest or payload_digest(ev.payload)
            expect = event_hash(
                prev_hash=ev.prev_hash,
                sequence=ev.sequence,
                type_=ev.type,
                payload_digest_s=pd,
            )
            if expect != ev.hash:
                raise HashChainBroken(f"seq={ev.sequence} hash mismatch")
            prev = ev.hash

    def append(
        self,
        type_: str,
        payload: Mapping[str, Any],
        *,
        actor: str | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        expected_sequence: int | None = None,
        max_retries: int = 3,
    ) -> EventEnvelope:
        if type_ not in _EVENT_TYPES:
            raise EventStoreError(f"unknown event type: {type_}")
        last_err: Exception | None = None
        for _ in range(max(1, max_retries)):
            try:
                return self._append_once(
                    type_,
                    payload,
                    actor=actor,
                    causation_id=causation_id,
                    correlation_id=correlation_id,
                    expected_sequence=expected_sequence,
                )
            except WriteContention as exc:
                if expected_sequence is not None:
                    raise
                last_err = exc
                continue
        raise WriteContention(str(last_err or "write contention"))

    def _append_once(
        self,
        type_: str,
        payload: Mapping[str, Any],
        *,
        actor: str | None,
        causation_id: str | None,
        correlation_id: str | None,
        expected_sequence: int | None,
    ) -> EventEnvelope:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT sequence, hash FROM events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    seq = 0
                    prev_hash: str | None = None
                else:
                    seq = int(row["sequence"]) + 1
                    prev_hash = str(row["hash"])
                if expected_sequence is not None and seq != int(expected_sequence):
                    raise WriteContention(
                        f"expected sequence {expected_sequence}, actual next {seq}"
                    )
                pd = payload_digest(payload)
                h = event_hash(
                    prev_hash=prev_hash, sequence=seq, type_=type_, payload_digest_s=pd
                )
                env = EventEnvelope(
                    schema=EVENT_SCHEMA,
                    event_id=f"ev-{uuid.uuid4().hex[:16]}",
                    sequence=seq,
                    prev_hash=prev_hash,
                    hash=h,
                    type=type_,
                    occurred_at=_utcnow(),
                    payload=dict(payload),
                    actor=actor,
                    payload_digest=pd,
                    causation_id=causation_id,
                    correlation_id=correlation_id or f"corr-{uuid.uuid4().hex[:12]}",
                )
                self._conn.execute(
                    """
                    INSERT INTO events (
                      sequence, event_id, schema, prev_hash, hash, type, occurred_at,
                      actor, payload, payload_digest, causation_id, correlation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        env.sequence,
                        env.event_id,
                        env.schema,
                        env.prev_hash,
                        env.hash,
                        env.type,
                        env.occurred_at,
                        env.actor,
                        json.dumps(env.payload, ensure_ascii=False),
                        env.payload_digest,
                        env.causation_id,
                        env.correlation_id,
                    ),
                )
                self._conn.execute("COMMIT")
                return env
            except WriteContention:
                self._conn.execute("ROLLBACK")
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise


def open_store(loop_dir: Path) -> EventStore:
    """Open EventStore at ``loop_dir/events.db``."""
    return EventStore(Path(loop_dir) / "events.db", lease_path=Path(loop_dir) / ".write_lease")


__all__ = [
    "EventEnvelope",
    "EventStore",
    "EventStoreError",
    "HashChainBroken",
    "WriteContention",
    "WriteLeaseError",
    "open_store",
    "payload_digest",
    "event_hash",
]
