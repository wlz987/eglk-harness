.PHONY: dist-check test-ci ci

dist-check:
	@echo "== dist-check (no upload) =="
	python -m pip install -q build twine
	rm -rf dist build *.egg-info src/*.egg-info
	python -m build
	python -m twine check dist/*
	@echo "dist-check: OK (twine check only — upload remains manual)"

test-ci ci:
	bash scripts/ci.sh
