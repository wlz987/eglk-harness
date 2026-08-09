## WA browser delivery (wa-browser MCP)

Read `.wa_hard_agent_response_hint.json` before `wa_write_agent_response`.

### Required `agent_response.json` shape (webarena-verified)

```json
{
  "task_type": "RETRIEVE",
  "status": "SUCCESS",
  "retrieved_data": [2],
  "error_details": null
}
```

- **RETRIEVE**: `retrieved_data` is a non-null array matching `results_schema` in the hint.
- **NAVIGATE** / **MUTATE**: `retrieved_data` must be `null`; completion is proven by HAR network evaluators.
- Do **not** use `answer`, `task_id`, `url`, or eglk envelope fields — MCP rejects non-official keys.

### Session workflow

1. `wa_start_session` (env `WA_BROWSER_TASK_ID` is authoritative).
2. Navigate / interact via wa-browser only (no second Playwright).
3. `wa_write_agent_response` with the official JSON object (not a wrapper).
4. `wa_finalize_session` to flush `network.har`.
5. Claim `done_progress: 1.0` only after `agent_runs/<task_id>/agent_response.json` and `network.har` exist.

### SWARM scout (wa-scout MCP, read-only)

Explorer/Verifier: use `scout_start` → `scout_snapshot` / `scout_list_links`. Scout writes only under `.eglk-harness/scout/` — never `agent_runs/`.
