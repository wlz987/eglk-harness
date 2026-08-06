# Changelog

## 0.1.0a1 — 2026-08-07

- Deepen `agent_logs` (format detect, steps, runtime signals, sidecars).
- Add `domain.plugins` + `eglk-harness plugin` CLI (computer-use opt-in; `run` never installs).
- Per-role `RoleBudgets` / `EGLK_TIMEOUT_*`; bypass prompt `en|zh` constraint blocks.
- Checker `evidence_guard` strips oracle/scorer keys (Gate stays truth-blind).
- Meter tokens/USD from adapter JSONL into `EpisodeResult`.
- Eval: `--external-score` for WA-Hard; OSWorld `path_hint`; weave CI script in design repo.
- Doctor reports plugins / budgets / prompt_language; richer default `config.toml`.
- Bypass roles honour `timeout_for_role`; `run` reuses installed plugin MCP (no install).
- Dashboard `/api/agent_logs`; status shows `usd_used` + plugin hints.
- `make maturity` / `scripts/maturity_gate.sh` local gate.
- Runtime bootstrap: `.env` → `config.toml` → CLI (packaging priority); `run --dashboard`.
- Protected paths: refuse Claim writes to `.goal.md` / `.goal_format.md` / `.eglk-harness/`.
- Packaging contract tests pin CLI surface to `design/kernel/packaging.md` §3.1.
