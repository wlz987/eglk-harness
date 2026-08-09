# Kernel vs eval · 控制核与评测边界

`eglk-harness` 是 **通用控制核**（Gate · 四相位 · WorldRef · Σ）。  
**Benchmark / Oracle / 套件工具名** 不属于内核契约。

## 内核（`domain/kernel` · `actors/` · `memory/skills/`）

| 机制 | 普适输入 |
|------|----------|
| Gate | Claim + Evidence + quota + repair_counts |
| Boundary | `MUST_EXIST` / `FORBIDDEN_*` / `USE_MCP:` 来自 **`.goal.md` + leaf_contract** |
| WorldRef restore | 保留顶目录 = env `EGLK_RESTORE_PRESERVE_DIRS` + `MUST_EXIST` 首段 + 通用默认（`artifacts/` …） |
| Skills | 角色行为与 JSON schema；**不写** `wa_*` 工具名或某 benchmark 路径 |
| Evidence guard | 剥离 `oracle` / `score` / `benchmark` 等键；机械合并 `boundary:` gaps |

内核 **不读** 评测终态判分器、HAR offline judge、external score JSON。

## 评测（`domain/eval/` · `bundled_eval/` · `eglk-harness eval`）

| 职责 | 说明 |
|------|------|
| Manifest / 离线 scorer | 分数写入 `.local/runs/`；**永不进 Gate** |
| `wa_hard` 等 suite 连接器 | 薄封装：物化 `.goal.md`、导入 `agent_runs`、外部 judge |
| `doctor` eval 探测 | **可选** 环境提示（Docker / Playwright）；失败多为 `warn_only` |

全量评测编排与 MCP 实现优先放在 **`experiment/eval/`**（与实现仓并列）。  
`bundled_eval/` 为可安装包内的 **示例/兼容副本**，非 SSOT。

## 冲突检查清单

1. **Skills 出现套件工具名** → 移到 goal constraints 或 experiment MCP instructions。
2. **WorldRef 硬编码 `agent_runs`** → 应仅由 `MUST_EXIST` 或 env 保留。
3. **Gate 读 Oracle/score** → 禁止；仅 Evidence guard 剥离。
4. **boundary 失败却 `perception_gap`** → Gate 应先 `boundary_unmet`（见 `gate_policy.md`）。
5. **Checker 边界失败却抬高 `audit_progress`** → `apply_boundary_to_evidence` 钳制 ≤0.45；normalize 不得覆盖。

设计 SSOT：`design/` · 实现默认：`eglk-harness/src/eglk_harness/domain/kernel/projections.py`。
