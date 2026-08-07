# Kernel + Shell 100% · eglk-harness

> 控制核 + 产品外壳实现闭合（**不含 PyPI**、不含墙钟实证 B 层）。

## 一键

```bash
bash experiment/eval/scripts/verify_kernel_shell_100.sh
cd eglk-harness && make kernel-shell-100
```

落盘：`experiment/runs/maturity_100/KERNEL_SHELL_100.json`

## 控制核 checklist

| # | 项 | 证据 |
|---|-----|------|
| 1 | 9 角色 skill 模板 + `render_prompt` | `domain/memory/skills/*.md` |
| 2 | Gate⊥评测正交测试 | `test_gate_eval_orthogonality` |
| 3 | 树/compile/governor/repair | `test_control_kernel` |
| 4 | Maker≠Checker / tools-off format-repair | `test_format_repair_tools_off` |
| 5 | 叶契约 / evidence guard | `test_leaf_contract`, `test_evidence_guard` |
| 6 | Σ / skill_lib / distill | `test_m4_swarm_sigma` |

## 产品外壳 checklist

| # | 项 | 证据 |
|---|-----|------|
| 1 | `status --json` · `read_only` · `hitl=false` | verify script |
| 2 | `doctor --json` eval 探针 | `eval_vllm_18000` … |
| 3 | `check-projections --json` | CI pin vs `projections.md` |
| 4 | `init` / `plugin` / `dashboard` / `eval` / `soak-bypass` | `cli.py` + tests |
| 5 | `implementation_complete` | `verify_implementation_100` |

## 与 LH 外壳差异（刻意）

- Dashboard **只读**（无 approve/inject）
- Gate **机械**（非 Manager LLM）
- eval 分数 **仅 Manifest**

## 仍须墙钟 / 人工（非实现缺口）

- Weave114 / OSWorld108 / TB242 全量跑完
- WA-Hard 258 任务级真完成
- PyPI upload（用户要求暂不管）
