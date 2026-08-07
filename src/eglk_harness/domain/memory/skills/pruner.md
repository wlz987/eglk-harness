# Pruner

Score Explorer alternatives as `score = prob * impact`. Mark `pruned: true` when `score < 0.2`.

Write only to `candidates/`. You may use **allowed tools/MCP** for observation
(`EGLK_MCP_ALLOW_PRUNER`); do not write `claims/`, `evidence/`, or `decisions/`.
Gate never sees Pruner output as a score input.

## Mechanical contract (harness)
- Orchestrator may prune deterministically from Explorer JSON; this skill documents LLM-assisted prune.
- Preserve Explorer `text`, `prob`, `impact`; add `score` and `pruned`.
- Do not invent new high-score alternatives to avoid pruning — that defeats SWARM economics.

## Scoring guidance
- `score < 0.2` → `pruned: true` (low value paths dropped from Maker prompt).
- Keep at least one non-pruned alternative when any path could satisfy acceptance.
- If all scores low, still prune honestly — Maker must reject in Claim `alternatives[]`.

## Hard rules
- Pruned lists are **not** Gate inputs, Oracle scores, or admit signals.
- Never write main ring directories.

## Output JSON shape

```json
{
  "role": "pruner",
  "tick": 0,
  "leaf_id": "root",
  "alternatives": [
    {"id": "alt-1", "text": "two packages + bridge", "prob": 0.75, "impact": 0.9, "score": 0.675, "pruned": false},
    {"id": "alt-2", "text": "monolith only", "prob": 0.3, "impact": 0.4, "score": 0.12, "pruned": true},
    {"id": "alt-3", "text": "skip tests", "prob": 0.1, "impact": 0.05, "score": 0.005, "pruned": true}
  ]
}
```

## Anti-patterns
- Setting every `pruned: false` to “help” Maker.
- Changing Explorer `text` to misrepresent a path.
- Using eval benchmark success as `impact`.
