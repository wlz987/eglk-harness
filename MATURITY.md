# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07. Four sibling repos. Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | **~94%** | Gate/树/Σ/WorldRef/SWARM；工具 profile 2+3；skills 对齐 |
| LH 产品外壳 | ≥90% | **~92%** | CLI/plugin/dashboard RO/JSON；release-check |
| 评测可复现 | ≥70% | **~88%** | 官方 Hard pack（681/522…）；CLI probe + **eval-tasks dry-run**；LH 三角 A/B |
| Live 长程 | ≥30min 或 split | **passed** | ACCEPTANCE elapsed_s=3966 |
| **相对自身设计总成熟** | ≥90% | **~94%** | 工程路径完备；全量榜与 PyPI 上传仍人工/env-gated |
| **相对 LH 产品** | 不对齐 | 外壳 ~92% | HITL/Manager 不追平 |

## 达档条件（相对自身设计）

已满足：控制核不变量 · 零 HITL · 长跑 · 工具策略 · WA 官方 ID pack · CLI dry-run · LH 三角接线。

## 人工 / 环境闸（不阻塞「工程成熟」）

1. WA Hard **真题** `eval-tasks`（需站点 + agent 轨迹；dry-run ≠ 真分）
2. PyPI `twine upload`（见 `RELEASE.md`）
3. Weave-114 / OSWorld-108 / TB 全量（`*_FULL=1`）

## 一键

```bash
make release-check && make lh-parity && make pulse
bash ../experiment/eval/scripts/sync_wa_hard_pack.sh
bash ../experiment/eval/scripts/run_wa_hard_eval_dry.sh
WA_HARD_LIVE=1 make eval-full-dry
```
