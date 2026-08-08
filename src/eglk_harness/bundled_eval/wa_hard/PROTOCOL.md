# WA-Hard PROTOCOL · external judge only

> Offline / external scores land in Manifest. **Never** write into Gate inputs.

## Dual track

| Track | When | How |
|-------|------|-----|
| HAR-offline | CI / no Docker | `--score-har fixtures/traces/*.json` (`eglk_wa_trace/0.1`) |
| Vendor / external | Docker + `vendor/webarena-verified` | official CLI → `--external-score` |

`fetch_wa_verified.sh` clones vendor; missing deps → structured skip (not CI fail).

## Flow

1. `eglk-harness eval --suite wa_hard --task-id <id> --prepare-only` materializes `.goal.md`.
2. **CI:** pass `--score-har` with a fixture trace; **or** live: run the official WebArena-Verified / ServiceNow harness **outside** eglk (Docker).
3. Produce a JSON result file, e.g.:

```json
{
  "task_id": "example",
  "scores": { "success": 1.0, "partial": 0.0 },
  "notes": "external judge"
}
```

4. Merge into Manifest (still Gate-blind):

```bash
eglk-harness eval --suite wa_hard --task-id <id> \
  --external-score /path/to/result.json --agent mock --max-ticks 1
```

## Forbidden

- Feeding `scores` / `oracle` / `pass_rate` into Gate or Checker Evidence.
- Treating WA-Hard success as admit authority.
