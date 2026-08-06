.PHONY: test projections soak weave maturity
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
