# Auxiliary eval packs (bundled)

Example task indices and thin fixtures shipped with **eglk-harness**.  
Offline / external scorers write Manifest scores only — **never Gate inputs**.

> **评测 SSOT** 在并列仓 `experiment/eval/`。本目录为可安装包内 **示例/兼容副本**。  
> 内核与 suite 无关 — 见 [`../../docs/KERNEL_VS_EVAL.md`](../../docs/KERNEL_VS_EVAL.md)。

Override or extend with `EGLK_EVAL_ROOT` pointing at a directory with the same layout
(`wa_hard/`, `weave_lh/`, `osworld_aux/`, `tb21/`, `weave_thin/`).

Optional live harness trees live under `$EGLK_EVAL_ROOT/vendor/` (not bundled).
