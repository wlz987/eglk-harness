# Pruner

Score Explorer alternatives as `prob * impact`. Mark `pruned: true` when score < 0.2.

Write only to `candidates/`. You may use **allowed tools/MCP** for observation
(`EGLK_MCP_ALLOW_PRUNER`); do not write `claims/`, `evidence/`, or `decisions/`.
Gate never sees your output.

Pruning is **mechanical** in the harness (reads Explorer candidates); this skill documents
the contract for soak / future LLM prune.

## Output / candidate shape

```json
{
  "role": "pruner",
  "tick": 0,
  "alternatives": [
    {"id": "alt-1", "text": "high-value path", "prob": 0.7, "impact": 0.8, "score": 0.56, "pruned": false},
    {"id": "alt-2", "text": "low-value decoy", "prob": 0.2, "impact": 0.1, "score": 0.02, "pruned": true}
  ]
}
```
