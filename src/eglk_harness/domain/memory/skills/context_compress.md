# context-compress (Phase 3)

Mechanical Phase-3 skill pin. Updates focus/uncertainty, decides next
`run_swarm` plan, merges Σ refined→active, archives candidates.

Never abort on `τ_focus` / `τ_unc`. Never read eval scorers.
Never write Gate inputs (claims/evidence/decisions).

Output surfaces: `ticks.jsonl`, `state.json`, `.eglk-harness/memory/sigma/active.json`.
