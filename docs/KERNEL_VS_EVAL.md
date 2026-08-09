# Kernel vs eval · 控制核与评测边界

`eglk-harness` 是 **通用控制核**（Gate · 四相位 · WorldRef · Σ）。  
**任何 benchmark / 套件特化** 应通过 **外部 eval 树** 注入，不写进内核 skills / Gate 逻辑。

## 内核（`domain/kernel` · `actors/` · `memory/skills/`）

| 机制 | 普适输入 |
|------|----------|
| Gate | Claim + Evidence + quota + repair_counts |
| Boundary | `MUST_EXIST` / `FORBIDDEN_*` / `USE_MCP:` ← **`.goal.md` + leaf_contract** |
| Packaged skills | `maker.md` / `checker.md` … — **无套件工具名** |
| WorldRef restore | `EGLK_RESTORE_PRESERVE_DIRS` + `MUST_EXIST` 首段 + 通用默认目录 |

内核 **不读** Oracle / 离线 scorer / external judge。

## 评测注入（`experiment/eval/`）

| 注入面 | 环境变量 / 路径 | 内容 |
|--------|-----------------|------|
| **Skill overlay** | `EGLK_SKILL_DIRS` 或 `$EGLK_EVAL_ROOT/skills/<role>.md` | 套件工具名、会话流程、截图预算 |
| **Per-run overlay** | `workdir/.eglk-harness/skill-overlay/<role>.md` | 单次 run 特化（可选） |
| **MCP** | `EGLK_MCP_CONFIG` 或 `workdir/.eglk-harness/mcp/*.mcp.json` | 浏览器/桌面 MCP 实现 |
| **Goal 约束** | `.goal.md` Constraints（eval driver 写入） | `MUST_EXIST`、交付路径、禁止前缀 |
| **Eval 根** | `EGLK_EVAL_ROOT` → `experiment/eval` | pack.json、fixtures、vendor |
| **Suite 连接器** | `$EGLK_EVAL_ROOT/lib/*.py` | `wa_hard` / `osworld` / … 动态加载 |

渲染顺序（`render_prompt`）：

```text
[SKILL packaged] → skill body → [INJECTED SKILL] overlay → leaf_contract block
```

设置 `EGLK_EVAL_ROOT=experiment/eval`；内核 wheel **不打包** pack 与 suite 模块。

## 仍留在 harness 的 eval 邻接层

| 模块 | 角色 |
|------|------|
| `domain/eval/loader.py` | 从 `EGLK_EVAL_ROOT/lib/` 动态加载 suite / probes |
| `domain/eval/eval_runner.py` | 通用 `prepare` / `score_offline`（无榜名硬编码优先） |
| `domain/eval/bypass_soak.py` | 旁路角色 soak（与 Gate 无关） |
| `domain/eval/paths.py` | `default_eval_root()` ← 仅 `EGLK_EVAL_ROOT` |

## 冲突检查清单

1. 内核 skill 出现 `wa_*` / 榜名 → 移到 `experiment/eval/skills/` 或 goal。
2. `default_eval_root()` 静默回落 bundled → **已移除**；必须设 `EGLK_EVAL_ROOT`。
3. Gate 读分数 → `evidence_guard` 剥离禁止键。
4. boundary 失败 → `boundary_unmet` 先于 `perception_gap`。
5. Checker 边界失败抬高 audit → `apply_boundary_to_evidence` 钳制；normalize 不覆盖。

设计 SSOT：`design/` · 阈值默认：`domain/kernel/projections.py`。
