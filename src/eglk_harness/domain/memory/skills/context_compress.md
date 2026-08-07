# context-compress (Phase 3)

Mechanical Phase-3 orchestration pin. After Gate on each tick:

1. Update `focus_score` / `uncertainty` from projections (signals only).
2. Plan next `run_swarm` from `τ_focus` / `τ_unc` / `SWARM_BUDGET_FLOOR`.
3. Merge `loop/.../sigma/refined/` → `.eglk-harness/memory/sigma/active.json` (Σ authority).
4. Archive spent `candidates/`; append `ticks.jsonl`; refresh `state.json`.

## Abort authority (critical)
- **Never abort** on `τ_focus` or `τ_unc` alone — signals for SWARM planning only.
- **Only** `cognitive_tokens` exhaustion or `repairs_max` triggers `abort`.
- `--max-ticks` is soft (Manifest); does not replace token/repair authority.

## Gate boundary
- Never read eval scorers, Oracle, `scenario.check`, WA/Weave/TB Manifest scores.
- Never write `claims/`, `evidence/`, `decisions/` in Phase 3.
- Gate decisions are inputs; Phase 3 does not reverse admit.

## Σ merge rules (summary)
- Refined items merge by `id` / similarity; bump `conf` on repeat hits.
- Archive or freeze low-conf noise; cap `SIGMA_ACTIVE_MAX` per projections.
- Loop `sigma/refined/` is staging only — memory `active.json` is SSOT.

## Tools
**No tools. No MCP. No world mutation.** Pure orchestrator + domain functions.

## Surfaces touched
`ticks.jsonl`, `state.json`, `.eglk-harness/memory/sigma/active.json`,
`candidates/` archive, skill_lib `distill_from_sigma` when configured.

## SWARM re-entry
- High `τ_unc` → more Explorer/Verifier budget next tick.
- Low focus → prefer Pruner-heavy Phase 0, not endless Maker retries in same session.
