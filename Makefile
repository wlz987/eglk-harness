.PHONY: test projections soak weave maturity maturity-100 implementation-100 kernel-shell-100 release-check eval-doctor eval-smokes pulse eval-full-dry sweep lh-parity lh-benchmark-practice dist-check verify-100 aggregate-empirical sync-weave-pack
test:
	pytest -q
projections:
	eglk-harness check-projections
soak:
	eglk-harness soak-bypass --agent mock
weave:
	bash ../experiment/eval/scripts/ci_weave_thin.sh
maturity:
	bash scripts/maturity_gate.sh
pulse:
	bash scripts/maturity_pulse.sh
eval-doctor:
	bash ../experiment/eval/scripts/doctor_eval_env.sh
aggregate-empirical:
	bash ../experiment/eval/scripts/aggregate_empirical_status.sh
sync-weave-pack:
	bash ../experiment/eval/scripts/sync_weave_lh_pack.sh
eval-smokes:
	bash ../experiment/eval/scripts/run_weave_lh_smoke.sh
	bash ../experiment/eval/scripts/run_osworld_smoke.sh
	bash ../experiment/eval/scripts/run_tb21_smoke.sh
	WA_HARD_LIMIT=3 bash ../experiment/eval/scripts/run_wa_hard_batch.sh
lh-parity:
	bash ../experiment/eval/scripts/run_lh_parity_matrix.sh
dist-check:
	@echo "== dist-check (no upload) =="
	python -m pip install -q build twine
	rm -rf dist build *.egg-info
	python -m build
	python -m twine check dist/*
	@echo "dist-check: OK (twine check only — upload remains manual)"
release-check:
	@echo "== release-check =="
	pytest -q
	eglk-harness check-projections
	eglk-harness soak-bypass --agent mock
	bash scripts/maturity_gate.sh
	python -c "from importlib.metadata import version; import eglk_harness; \
print('package', eglk_harness.__version__); \
assert eglk_harness.__version__"
	eglk-harness --help >/dev/null
	eglk-harness eval --help >/dev/null
	@echo "release-check: OK"

eval-full-dry:
	bash ../experiment/eval/scripts/run_wa_hard_live_attempt.sh
	bash ../experiment/eval/scripts/run_wa_hard_eval_dry.sh
	bash ../experiment/eval/scripts/run_wa_hard_official_score_demo.sh
	bash ../experiment/eval/scripts/run_weave_lh_full.sh
	bash ../experiment/eval/scripts/run_osworld_full.sh
	bash ../experiment/eval/scripts/run_tb21_full.sh
sweep:
	bash scripts/full_maturity_sweep.sh

lh-benchmark-practice:
	bash ../experiment/eval/scripts/run_lh_benchmark_practice.sh

verify-100:
	bash ../experiment/eval/scripts/verify_maturity_100.sh

implementation-100:
	bash ../experiment/eval/scripts/verify_implementation_100.sh

kernel-shell-100:
	bash ../experiment/eval/scripts/verify_kernel_shell_100.sh

benchmark-matrix:
	nohup bash ../experiment/eval/scripts/run_benchmark_matrix_18000.sh \
	  > ../experiment/runs/benchmark_matrix_18000/nohup.out 2>&1 &

maturity-100:
	bash ../experiment/eval/scripts/run_maturity_100.sh
