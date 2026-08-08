.PHONY: test projections soak maturity release-check eval-compare dist-check pulse sweep long-natural demo-gif
test:
	pytest -q
projections:
	eglk-harness check-projections
soak:
	eglk-harness soak-bypass --agent mock
maturity:
	bash scripts/maturity_gate.sh
pulse:
	bash scripts/maturity_pulse.sh
eval-compare:
	bash scripts/eval_compare.sh
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

sweep:
	bash scripts/full_maturity_sweep.sh

long-natural:
	bash scripts/run_long_natural_split.sh

demo-gif:
	bash scripts/generate_demo_gif.sh
