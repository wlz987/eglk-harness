# Maturity self-assessment · eglk-harness 0.1.0b1

Updated: 2026-08-07. Four sibling repos. Scores/scorers never feed Gate.

| 轴 | 目标 | 自评 | 证据 |
|----|------|------|------|
| 控制核 | ≥90% | **~95%** | Gate/树/Σ/WorldRef/SWARM；工具 profile 2+3；skills 加厚 |
| LH 产品外壳 | ≥90% | **~93%** | CLI/plugin/dashboard RO/JSON；`make dist-check`；release-check |
| 评测可复现 | ≥70% | **~92%** | 官方 Hard pack；**eval-tasks 真分路径**（demo 107/108 + `--score-agent-runs`）；LH 三角 A/B |
| Live 长程 | ≥30min 或 split | **passed** | ACCEPTANCE elapsed_s=3966 |
| **相对自身设计总成熟** | ≥90% | **~95%** | 官方判分工程路径已闭合；Hard 站点真跑 + PyPI upload 仍人工/env-gated |
| **相对 LH 产品** | 不对齐 | 外壳 ~93% | HITL/Manager 不追平 |

## 达档条件（相对自身设计）

已满足：控制核不变量 · 零 HITL · 长跑 · 工具策略 · WA 官方 ID pack · CLI dry-run ·
**官方 eval-tasks → Manifest ingest** · LH 三角接线 · skill 操作厚度。

## 人工 / 环境闸（不阻塞「工程成熟」）

1. WA Hard **站点真跑**（Hard ids 的 agent 轨迹；demo 107/108 ≠ Hard 科学声明）
2. PyPI `twine upload`（见 `RELEASE.md`；本地 `make dist-check` 已覆盖 check）
3. Weave-114 / OSWorld-108 / TB 全量（`*_FULL=1`）

## 一键

```bash
make release-check && make lh-parity && make pulse
make dist-check   # build + twine check；不上传
bash ../experiment/eval/scripts/sync_wa_hard_pack.sh
bash ../experiment/eval/scripts/run_wa_hard_eval_dry.sh
bash ../experiment/eval/scripts/run_wa_hard_official_score_demo.sh
WA_HARD_LIVE=1 make eval-full-dry
```
