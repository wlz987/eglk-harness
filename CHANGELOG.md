# Changelog

## 0.1.0b1 — 2026-08-07

- Role tool profiles (policy 2+3): session roles may hold tools/MCP; `EGLK_MCP_ALLOW_<ROLE>` allowlists; format-repair stays tools-off; SWARM still cannot write claims/evidence/decisions
- WA-Hard `probe_official_cli` (Docker `--help`) when `WA_HARD_LIVE=1`
- Full maturity empirical track: `weave_lh` / `tb21` / OSWorld / eval vendor doctor
- Doctor reports eval WA/LH/tb21 hints; `status --json` / `doctor --json`
- Parse Claim/Evidence from Codex `command_execution` stdout; format-repair tools-off
- Long-run ACCEPTANCE passed (elapsed≥30min)

## 0.1.0a2 — 2026-08-07

- WA-Hard dual-track: `score_har_offline` / `--score-har` (CI fixtures) + optional vendor status skip
- Natural multi-leaf: integration coverage without pre-split; `run_long_natural_split.sh`
- `make release-check` packaging gate; RELEASE.md install narrative

## 0.1.0a1

- Initial maturity B surface: parse harden, WA-Hard batch, swarm/multi-leaf live gates
