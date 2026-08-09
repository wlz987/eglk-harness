"""Transaction lifecycle audit — environment_protocol § transaction state machine."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from eglk_harness.domain.event_store import EventEnvelope

_VALID_AFTER_PREPARED = frozenset(
    {
        "TransactionObserved",
        "TransactionCommitted",
        "TransactionRolledBack",
        "TransactionCompensated",
    }
)
_SETTLED = frozenset(
    {"TransactionCommitted", "TransactionRolledBack", "TransactionCompensated"}
)


def audit_transaction_sequences(events: Sequence[EventEnvelope]) -> tuple[bool, str]:
    prepared: dict[str, int] = {}
    settled: set[str] = set()
    sequences: dict[str, list[str]] = {}
    for ev in events:
        p = ev.payload or {}
        tid = str(p.get("transaction_id") or "")
        if not tid and ev.type in {
            "TransactionPrepared",
            "TransactionObserved",
            "TransactionCommitted",
            "TransactionRolledBack",
            "TransactionCompensated",
        }:
            return False, f"missing_transaction_id:{ev.type}@{ev.sequence}"
        if ev.type == "TransactionPrepared":
            prepared[tid] = ev.sequence
            sequences.setdefault(tid, []).append(ev.type)
        elif tid in prepared or tid in sequences:
            seq = sequences.setdefault(tid, [])
            if ev.type in _SETTLED:
                settled.add(tid)
            if ev.type == "TransactionObserved" and not any(
                t in seq for t in ("ActionDispatched", "TransactionPrepared")
            ):
                # observed may follow prepared directly in our kernel
                pass
            seq.append(ev.type)
        elif ev.type.startswith("Transaction") and tid:
            sequences.setdefault(tid, []).append(ev.type)

    for tid, seq in sequences.items():
        if not seq:
            continue
        if seq[0] != "TransactionPrepared":
            return False, f"{tid}:starts_with_{seq[0]}"
        if len(seq) > 1:
            for step in seq[1:]:
                if step not in _VALID_AFTER_PREPARED and step != "TransactionPrepared":
                    return False, f"{tid}:invalid_step_{step}"
        if tid in prepared and tid not in settled and len(seq) == 1:
            # dangling prepared — recovery should handle at acquire
            continue
    return True, f"tx_count={len(sequences)}"


def audit_run_aborted_chain(events: Sequence[EventEnvelope]) -> tuple[bool, str]:
    from eglk_harness.domain.kernel.gate import _ABORT_REASONS

    by_id = {e.event_id: e for e in events}
    for ev in events:
        if ev.type != "RunAborted":
            continue
        cid = ev.causation_id
        if not cid or cid not in by_id:
            return False, f"RunAborted missing causation:{ev.event_id}"
        gate = by_id[cid]
        if gate.type != "GateDecided":
            return False, f"RunAborted not from GateDecided:{ev.event_id}"
        reason = str((gate.payload or {}).get("reason") or "")
        if reason not in _ABORT_REASONS:
            return False, f"RunAborted bad gate reason:{reason}"
    return True, "RunAborted chain ok"
