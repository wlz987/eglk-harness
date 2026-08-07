# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07. Workspace: four sibling git repos (`design`/`docs`/`eglk-harness`/`experiment`). Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | ~93% | Gate/树/Σ/WorldRef/SWARM；**角色工具 profile 2+3**；projections pin |
| LH 产品外壳 | ≥90% | ~91% | init/doctor/run/plugin/dashboard RO / JSON CLI / eval / release-check |
| 评测可复现 | ≥70% | ~82% | HAR-offline；三角 smoke；WA vendor + **official CLI probe**；`LH_PARITY` |
| Live 长程 | 自然 split 或 ≥30min | **passed** | `ACCEPTANCE` elapsed_s=3966；root admit |
| **相对自身设计总成熟** | ≥90% | **~92%** | 长跑达档；工具策略已改；Hard 真分仍外置 |
| **相对 LH 产品完成度** | 不对齐目标 | 外壳 ~91% | HITL/Manager **不追平** |

## 已完成（勿重复）

- `long_natural_split` ACCEPTANCE ✅
- LH 三角层 A/B + `make lh-parity` ✅
- 工具策略 **2+3**：会话角色默认可持工具；`EGLK_MCP_ALLOW_<ROLE>` / `EGLK_TOOLS_OFF_ROLES`；旁路零写主环；format-repair tools-off ✅
- WA official CLI Docker `--help` probe（`WA_HARD_LIVE=1`）✅

## 仍开放（高杠杆）

1. WA-Hard **真题 eval-tasks** limit≤3（probe ≠ 真分）
2. PyPI 正式发布（人工 `RELEASE.md`）
3. Weave-114 / OSWorld-108 / TB 层 C 全量（env-gated）

## 一键

```bash
make release-check
make lh-parity
make pulse
WA_HARD_LIVE=1 make eval-full-dry   # includes official CLI probe when live
```
