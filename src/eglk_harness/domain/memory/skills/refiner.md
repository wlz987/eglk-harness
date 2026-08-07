# Refiner

Write Σ staging items under `sigma/refined/` only. Never merge into memory Σ yourself
(Phase 3 owns merge). Never feed Gate. You may use **allowed tools/MCP** for observation
(`EGLK_MCP_ALLOW_REFINER`); do not write `claims/`, `evidence/`, or `decisions/`.

Prefer lessons from repair gaps and step_review; hits from admit benefits.

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
