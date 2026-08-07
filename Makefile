.PHONY: test projections soak weave maturity release-check eval-doctor eval-smokes
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
eval-doctor:
	bash ../experiment/eval/scripts/doctor_eval_env.sh
eval-smokes:
	bash ../experiment/eval/scripts/run_weave_lh_smoke.sh
	bash ../experiment/eval/scripts/run_osworld_smoke.sh
	WA_HARD_LIMIT=3 bash ../experiment/eval/scripts/run_wa_hard_batch.sh
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
