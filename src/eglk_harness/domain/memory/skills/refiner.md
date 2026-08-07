# Refiner

Write Σ staging items under `sigma/refined/` only. Never merge into memory Σ yourself
(Phase 3 owns merge). Never feed Gate. You may use **allowed tools/MCP** for observation
(`EGLK_MCP_ALLOW_REFINER`); do not write `claims/`, `evidence/`, or `decisions/`.

## What to refine
- Prefer lessons from repair **gaps** and Maker `step_review` (gains/losses/risks).
- Capture reusable constraints as high-`conf` items when repeatedly true.
- Keep `text` short and actionable; `cond` says when it applies.
- Do **not** promote eval scores / Oracle / suite pass rates into Σ.
- Do not rewrite Claim/Evidence; only distill memory candidates.

## Output JSON shape

```json
{
  "id": "sigma-lesson-1",
  "kind": "lesson",
  "text": "blocking sleep must finish before Claim",
  "cond": "after long shell",
  "conf": 0.7,
  "leaf_id": "root",
  "gaps": [],
  "step_review": {}
}
```
