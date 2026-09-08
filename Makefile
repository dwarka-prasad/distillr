.PHONY: install test lint bench payloads fmt
install:        ## editable install with dev extras
	pip install -e '.[dev]'
test:           ## unit tests
	pytest -q
lint:           ## ruff
	ruff check . && ruff format --check .
fmt:
	ruff format . && ruff check --fix .
payloads:       ## regenerate benchmark payloads
	python benchmarks/generate.py
bench:          ## run the Phase 0 benchmark and write benchmarks/RESULTS.md
	python benchmarks/run.py
