# Contributing to Distillr

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
make test lint bench
```

## Layout

```
distillr/core/stages/   retrieve.py, semantic.py, encode.py, audit.py, base.py (Stage contract)
distillr/core/          payload.py (shape detection), tokenizers.py, toon.py, pipeline.py, ledger.py
distillr/cli.py         Typer CLI
benchmarks/             generate.py (deterministic payloads with needles), run.py (savings + recall), RESULTS.md
tests/                  pytest, no network
docs/                   spec.md, design.md
site/                   the GitHub Pages site, built from the markdown in this repo
```

## Rules of the road

- A stage must record every removal as a `Removal` with a path, reason and preview. If a change removes data
  silently, it is a bug.
- Token counts are measured with tiktoken. Never estimate silently; the `(approx)` label exists for the fallback.
- The encode stage must stay lossless. Add a round-trip test for any new format.
- Run `make bench` before and after a change to Stage 1 or Stage 3 and paste the diff in the PR. Needle recall
  must stay at 100%.
- Conventional commits. Ruff formats; line length 140.

## Where to start

See [ROADMAP.md](ROADMAP.md). Issues tagged `good first issue` are small and documented; `help wanted` are open
to anyone. Comment on the issue to claim it.
