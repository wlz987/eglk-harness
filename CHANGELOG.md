# Changelog

## 0.1.0b1 — 2026-08-09

- 实现包移除内置验证套件；角色 skill 渐进披露与 goal 边界校验
- MCP TOML 加载、SWARM 工具 profile、manifest 预算与 format-repair 加固

## 0.1.0b1 — 2026-08-07

- Official WA `eval-tasks` score path: `score_from_eval_result` / `ingest_agent_runs` /
  `run_eval_tasks` + CLI `--score-agent-runs` (Manifest-only; never Gate)
- `run_wa_hard_official_score_demo.sh` (vendor demo 107/108 true scores)
- SWARM/旁路 skills thickened; `make dist-check` (build + twine check, no upload)
- Role tool profiles (policy 2+3); skills updated for allowlisted tools
- WA-Hard pack synced to official Hard ids (681/522…); `sync_wa_hard_pack.sh` + `eval-tasks --dry-run`
- WA-Hard `probe_official_cli` (Docker `--help`) when `WA_HARD_LIVE=1`
- Full maturity empirical track: `weave_lh` / `tb21` / OSWorld / eval vendor doctor
- Doctor reports eval WA/LH/tb21 hints; `status --json` / `doctor --json`
- Parse Claim/Evidence from Codex `command_execution` stdout; format-repair tools-off
- Long-run ACCEPTANCE passed (elapsed≥30min)

## 0.1.0a2 — 2026-08-07

- WA-Hard dual-track: `score_har_offline` / `--score-har` (CI fixtures) + optional vendor status skip
- Natural multi-leaf: integration coverage without pre-split; long-run natural split script
- RELEASE.md install narrative; packaging gate moved out of implementation tree

## 0.1.0a1

- Initial maturity B surface: parse harden, WA-Hard batch, swarm/multi-leaf live gates
