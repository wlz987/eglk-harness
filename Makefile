.PHONY: test projections soak weave maturity release-check
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
