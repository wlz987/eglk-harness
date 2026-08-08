# Auxiliary eval packs (bundled)

Example task indices and thin fixtures shipped with **eglk-harness**.  
Offline / external scorers write Manifest scores only — **never Gate inputs**.

Override or extend with `EGLK_EVAL_ROOT` pointing at a directory with the same layout
(`wa_hard/`, `weave_lh/`, `osworld_aux/`, `tb21/`, `weave_thin/`).

Optional live harness trees live under `$EGLK_EVAL_ROOT/vendor/` (not bundled).
