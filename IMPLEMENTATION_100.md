# Implementation 100% · eglk-harness

> **实现层 100%** = 代码 + CLI + 探针 + 配置 + CI 全绿；**不含**墙钟实证跑完（B 层）。

## 一键验收

```bash
bash experiment/eval/scripts/verify_implementation_100.sh
# 或
cd eglk-harness && make implementation-100
```

落盘：`experiment/runs/maturity_100/IMPLEMENTATION_100.json` · `LIVE_MATURITY.md`（finalize）。

## Checklist

| # | 项 | 验收 |
|---|-----|------|
| 1 | pytest + projections + mock soak | verify 内自动跑 |
| 2 | `eglk-harness doctor --json` eval 探针 | eval_vllm / playwright / wa_browser / weave_pack |
| 3 | `eval_env_probes.collect_eval_env_status` | weave≥100 · vendor 齐 |
| 4 | WA `trim` + `build_pack_from_vendor_assets` | 258 Hard 索引可读 |
| 5 | `finalize_live_maturity.sh` | LIVE_MATURITY.md |
| 6 | `verify_maturity_100` config_complete | 配置层交叉验证 |

## 与 B 层（实证）边界

| 层 | 命令 | 含义 |
|----|------|------|
| **实现 100%** | `verify_implementation_100.sh` | 可立即 PASS |
| **配置 100%** | `verify_maturity_100.sh` | env + 脚本 + list-tasks |
| **实证 B 层** | `aggregate_empirical_status.sh` | Weave114/OSWorld108/TB242 墙钟 |

分数永不进 Gate；WA-Hard 仍为主尺叙事。

## 全量索引脚本

```bash
bash experiment/eval/scripts/sync_weave_lh_pack.sh      # weave 116
bash experiment/eval/scripts/sync_wa_hard_full_index.sh # wa 258 → pack.json
bash experiment/eval/scripts/sync_wa_hard_pack.sh       # subset-export 或 vendor 回退
```

## Live 长程 finalize（不重跑 40min）

```bash
LIVE_LONG_SKIP_BENCH=1 LIVE_LONG_SKIP_SOAK=1 \
  bash experiment/eval/scripts/finalize_live_maturity.sh
```
