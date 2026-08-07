# Maturity 100% · 定义与验收

> Updated: 2026-08-08 · eglk-harness `0.1.0b1`  
> **100% 分两层**：**配置+实现闭合**（可立即验收）与 **实证全量跑完**（墙钟依赖）。

## 两层 100%

| 层 | 含义 | 验收命令 | 当前 |
|----|------|----------|------|
| **A. 配置+实现 100%** | 脚本/包/文档/CI 全绿；env 完整；list-tasks 规模对齐 LH | `bash experiment/eval/scripts/verify_maturity_100.sh` | 目标 **PASS** |
| **B. 实证 100%** | Live 长程 + Weave114 + OSWorld108 + TB242 + WA 主尺真分落盘 | `aggregate_empirical_status.sh` → `B_LAYER.md` | 墙钟进行中 |

分数 **永不** 进 Gate；WA-Hard 仍为主尺叙事。

## 一键（配置 100% + 启动实证）

```bash
# 推荐：验证 → CI gate → dist-check → 附着/启动全量编排
bash experiment/eval/scripts/run_maturity_100.sh

# 仅验证配置层（不跑 pytest）
SKIP_LH_PARITY=1 bash experiment/eval/scripts/verify_maturity_100.sh
```

## A 层 checklist（配置+实现）

| # | 项 | 证据 |
|---|-----|------|
| 1 | LH 三角 suite + WA 主尺 `--list-tasks` | weave≥100 · osworld≥108 · tb21≥242 · wa≥3 |
| 2 | 全量剧本脚本 | `run_full_complete_18000.sh` · `run_weave_18000.sh` · `run_osworld_live.sh` · `run_tb21_*` · `run_aux_*` |
| 3 | Live 长程 | `run_live_long_maturity.sh` · maker≥3600 · sleep≥2400 |
| 4 | 文档 | `LH_PARITY.md` · 四套 `FULL_REPRO.md` · `COMPARE_LH.md` |
| 5 | CI | `make lh-parity` · `maturity_gate.sh` · `make dist-check` |
| 6 | 环境 | `lh_benchmark.env`（从 `.example` 复制）· HF_TOKEN · `:18000` tunnel `0.0.0.0` |
| 7 | 硬约束 | Gate⊥评测 · 零 HITL · Maker≠Checker · 禁止 `:28000` |

## B 层 checklist（实证）

| # | 项 | 落盘位置 |
|---|-----|----------|
| 1 | Live 长程 ≥40min + soak | `experiment/runs/live_long_maturity/LIVE_MATURITY.md` |
| 2 | Weave 114 | `WeaveBench/results/full_*/summary_*.json` |
| 3 | OSWorld 108 | `experiment/runs/osworld_live/` |
| 4 | TB 2.1 full | `experiment/runs/tb21_full/FULL_STATUS.json` + `tb` output |
| 5 | WA-Hard | `experiment/runs/wa_hard_*` + external-score Manifest |
| 6 | 收口状态 | `experiment/runs/full_complete_18000/COMPLETE.md` |

## 相对 LH-harness

| 维度 | eglk 100% 定义 | LH |
|------|----------------|-----|
| 外壳同形 | init/doctor/run/plugin/eval 全接线 | ~同 |
| 三角规模 | pack 索引对齐 114/108/242 | 官方 frozen + 榜面 |
| 控制核 | **机械 Gate · 零 HITL**（不追 LH Manager） | LLM Manager + HITL |
| 社区/发布 | dist-check ✅ · PyPI upload 人工 | 已发布 |

**相对 eglk 设计目标的 LH 拟合 ~40%** 是预期——不是缺口。

## 监控

```bash
bash experiment/eval/scripts/aggregate_empirical_status.sh
cat experiment/runs/maturity_100/B_LAYER.md
tail -f experiment/runs/full_complete_18000/nohup.out
cat experiment/runs/maturity_100/VERIFY_100.json
```

## 仍须人工（不算实现缺口）

1. PyPI `twine upload`（凭证）
2. WA-Hard **任务级真完成**（HAR/MCP 路径已配置；`har-smoke` + `trim-network-logs` 验证基础设施）
3. 论文站 **公网托管**（静态页 `docs/site/` + 本地 GIF 生成）
