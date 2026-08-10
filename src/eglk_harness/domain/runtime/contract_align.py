"""Mechanical alignment of Maker/Checker outputs to active WorkContract bindings."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

PLACEHOLDER_CONTRACT_REF = "wc-unknown"
PLACEHOLDER_OBLIGATION_ID = "ob-unknown"


def _as_list(x: Any) -> list[Any]:
    return list(x) if isinstance(x, (list, tuple)) else []


def render_contract_binding_block(
    contract_ref: str,
    obligation_refs: Sequence[str],
    *,
    world_revision: int | None = None,
) -> str:
    cref = str(contract_ref or "").strip()
    refs = [str(x).strip() for x in obligation_refs if str(x).strip()]
    if not cref and not refs:
        return ""
    lines = ["[WORK_CONTRACT_BINDING]"]
    if cref:
        lines.append(f"contract_ref: {cref}")
    if world_revision is not None:
        lines.append(f"world_revision_base: {int(world_revision)}")
    if refs:
        lines.extend(
            [
                "obligation_refs (Checker: one verdict per id — copy exactly):",
                *[f"  - {oid}" for oid in refs],
                "Never use ob-unknown or placeholder obligation ids.",
            ]
        )
    return "\n".join(lines)


def _is_placeholder_contract_ref(ref: str) -> bool:
    r = str(ref or "").strip()
    return not r or r == PLACEHOLDER_CONTRACT_REF


def _is_placeholder_obligation_id(oid: str) -> bool:
    o = str(oid or "").strip()
    return not o or o == PLACEHOLDER_OBLIGATION_ID


def align_claim_to_contract(
    claim: Mapping[str, Any],
    *,
    contract_ref: str,
    obligation_refs: Sequence[str] | None = None,
    world_revision_base: int | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    """Stamp authoritative contract_ref / revision on Maker output before Gate."""
    out = dict(claim)
    cref = str(contract_ref or "").strip()
    if cref and _is_placeholder_contract_ref(str(out.get("contract_ref") or "")):
        out["contract_ref"] = cref
    elif cref and not out.get("contract_ref"):
        out["contract_ref"] = cref
    if world_revision_base is not None and "world_revision_base" not in out:
        out["world_revision_base"] = int(world_revision_base)
    if node_id and not out.get("node_id"):
        out["node_id"] = node_id
    # obligation_refs are not claim fields — binding is via contract_ref only
    _ = obligation_refs
    return out


def _merge_verdicts(primary: Mapping[str, Any], secondary: Mapping[str, Any]) -> dict[str, Any]:
    """Prefer primary status/gaps; union attestations."""
    a = dict(primary)
    b = dict(secondary)
    atts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in (a.get("attestations") or [], b.get("attestations") or []):
        for att in src:
            if not isinstance(att, Mapping):
                continue
            key = str(att.get("digest") or att.get("raw_ref") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            atts.append(dict(att))
    status = str(a.get("status") or b.get("status") or "unsatisfied")
    if status != "satisfied" and str(b.get("status") or "") == "satisfied":
        status = "satisfied"
    gaps = [str(g) for g in _as_list(a.get("gaps")) if str(g).strip()]
    for g in _as_list(b.get("gaps")):
        gs = str(g)
        if gs.strip() and gs not in gaps:
            gaps.append(gs)
    return {
        "obligation_id": str(a.get("obligation_id") or b.get("obligation_id") or ""),
        "status": status,
        "attestations": atts,
        "gaps": gaps,
        "defect_suspected": bool(a.get("defect_suspected") or b.get("defect_suspected")),
    }


def align_evidence_to_contract(
    evidence: Mapping[str, Any],
    *,
    contract_ref: str,
    obligation_refs: Sequence[str],
    world_revision: int | None = None,
) -> dict[str, Any]:
    """Map Checker verdicts to WorkContract.obligation_refs for mechanical Gate."""
    out = dict(evidence)
    refs = [str(x).strip() for x in obligation_refs if str(x).strip()]
    cref = str(contract_ref or "").strip()
    if cref and _is_placeholder_contract_ref(str(out.get("contract_ref") or "")):
        out["contract_ref"] = cref
    elif cref and not out.get("contract_ref"):
        out["contract_ref"] = cref

    rev = world_revision
    if rev is None and "world_revision" in out:
        try:
            rev = int(out["world_revision"])
        except (TypeError, ValueError):
            rev = None

    verdicts_in = [dict(v) for v in _as_list(out.get("verdicts")) if isinstance(v, Mapping)]
    if not refs:
        out["verdicts"] = verdicts_in
        return out

    by_id: dict[str, dict[str, Any]] = {}
    orphans: list[dict[str, Any]] = []
    for verdict in verdicts_in:
        oid = str(verdict.get("obligation_id") or "").strip()
        if oid in refs:
            if oid in by_id:
                by_id[oid] = _merge_verdicts(by_id[oid], verdict)
            else:
                by_id[oid] = verdict
        elif _is_placeholder_obligation_id(oid):
            orphans.append(verdict)
        else:
            orphans.append(verdict)

    if orphans:
        if len(refs) == 1:
            merged = orphans[0]
            for extra in orphans[1:]:
                merged = _merge_verdicts(merged, extra)
            merged["obligation_id"] = refs[0]
            if refs[0] in by_id:
                by_id[refs[0]] = _merge_verdicts(by_id[refs[0]], merged)
            else:
                by_id[refs[0]] = merged
        else:
            for i, oid in enumerate(refs):
                if oid in by_id:
                    continue
                src = orphans[min(i, len(orphans) - 1)]
                vd = dict(src)
                vd["obligation_id"] = oid
                by_id[oid] = vd

    out_verdicts: list[dict[str, Any]] = []
    for oid in refs:
        if oid in by_id:
            vd = dict(by_id[oid])
            vd["obligation_id"] = oid
            out_verdicts.append(vd)
        else:
            out_verdicts.append(
                {
                    "obligation_id": oid,
                    "status": "unsatisfied",
                    "attestations": [],
                    "gaps": ["no verdict for obligation"],
                    "defect_suspected": False,
                }
            )

    if rev is not None:
        out["world_revision"] = int(rev)
        for vd in out_verdicts:
            for att in vd.get("attestations") or []:
                if isinstance(att, dict):
                    att["world_revision"] = int(rev)

    out["verdicts"] = out_verdicts
    return out
