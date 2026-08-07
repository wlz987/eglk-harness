# context-compress (Phase 3)

Mechanical Phase-3 skill pin (orchestrator-owned). After Gate:

1. Update `focus_score` / `uncertainty` (signals only).
2. Decide next `run_swarm` plan from projections (`τ_focus` / `τ_unc` / budget floor).
3. Merge Σ `refined/` → memory `active.json` (authority under `.eglk-harness/memory/`).
4. Archive spent candidates; append `ticks.jsonl` / refresh `state.json`.

## Hard rules
- **Never abort** on `τ_focus` / `τ_unc` — those are signals, not halt conditions.
- Abort authority remains `cognitive_tokens` + `repairs_max` only.
- Never read eval scorers / Oracle / scenario.check.
- Never write Gate inputs (`claims/`, `evidence/`, `decisions/`).
- No tools. No MCP. No world mutation.

## Surfaces
`ticks.jsonl`, `state.json`, `.eglk-harness/memory/sigma/active.json`,
loop `candidates/` archive as designed.
