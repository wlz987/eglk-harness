---
name: context_compress
description: Orchestrator pin for Phase 3 tick signals — not an LLM episode skill.
---

# context-compress (Phase 3)

Mechanical Phase-3 orchestration pin. After Gate on each tick:

1. Update `focus_score` / `uncertainty` from projections (diagnostic only).
2. Plan next SWARM from **candidate backlog** + `SWARM_BUDGET_FLOOR` (not `τ_focus` / `τ_unc` abort).
3. **Stage** tick lessons under `loop/.../sigma/refined/` (mechanical snapshot only).
4. Archive spent `candidates/`; append `ticks.jsonl`; export `projections/run_projection.json`.

**Refiner** runs **once at run end** (terminal `succeeded`/`aborted`/`invalid`/`faulted`) — see `refiner_batch.run_end_refiner_batch`. It polishes staged `sigma/refined/` and flushes into lifecycle `candidate/` (never `active` in the same run).

## Abort authority (critical)
- **Never abort** on `focus_score` or `uncertainty` alone — diagnostic signals only.
- **Only** `cognitive_tokens` exhaustion or `repairs_max` triggers `abort`.
- `--max-ticks` is soft (Manifest); does not replace token/repair authority.

## Gate boundary
- Never read eval scorers, Oracle, `scenario.check`, WA/Weave/TB Manifest scores.
- Never write `claims/`, `evidence/`, `decisions/` in Phase 3.
- Gate decisions are inputs; Phase 3 does not reverse admit.

## Σ lifecycle (summary)
- Per-tick: mechanical stage → `loop/sigma/refined/` (not readable by same run).
- Run end: Refiner batch → `memory/sigma/candidate/` via `MemoryCandidateWritten`.
- Promotion to `active` requires later independent runs (see `context.md` §3).

## Tools
**No tools. No MCP. No world mutation.** Pure orchestrator + domain functions.

## Surfaces touched
`ticks.jsonl`, `projections/run_projection.json`, `loop/sigma/refined/`, lifecycle `candidate/`, `candidates/` archive.

## SWARM re-entry
- `len(candidates/) > N_max` → CandidateSelector + Verifier.
- Budget floor → throttle Explorer/Verifier; never abort on SWARM alone.
