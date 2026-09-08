# Design notes

## Why the ledger is in Phase 0

The spec's key principle: observability must never feel bolted on. So every `Pipeline.run` produces a
`CompressionResult` with per-stage `StageReport`s and a removal `manifest`, and `Ledger.record` writes the
same shape the hosted dashboard will read later. SQLite locally, Postgres hosted, one schema.

## Measuring honestly

- **Baseline** is the payload as the team would paste it: the original file text when we have it, otherwise
  `json.dumps(indent=2)`. Measuring against minified JSON would flatter the encode stage.
- **Between stages** structured data is rendered as pretty JSON so Stage 1 savings reflect *content removed*, not
  formatting. Stage 3 then shows the format layer's contribution on its own. The first stage's `tokens_before`
  is pinned to the true baseline so the per-stage numbers add up to the total.
- **Tokenizers** are real (tiktoken). When the encoding files cannot be loaded we fall back to a heuristic and
  the counter's label carries `(approx)`, which the CLI surfaces as a warning and the ledger stores verbatim.

## Stage contract

```python
class Stage(Protocol):
    name: str

    def run(self, data, ctx: Context) -> tuple[data, StageReport]: ...
```

Stages are dataclasses with explicit knobs. Each knob maps to a `Removal.reason` so the manifest explains
itself ("low relevance (score 1.81)", "in drop_fields", "string over 400 chars", "beyond top_k=12").

## Retrieval ranking

BM25 over a simple word tokenizer with a stop list. It is not embeddings, on purpose: zero dependencies,
deterministic, fast, and good enough to pass the Phase 0 gate on structured data where the query names
entities (ids, names, cities, error strings). `RetrieveStage(scorer=...)` accepts any
`(query, texts) -> scores` callable for embedding-based ranking later.

Chat history gets special handling: system messages and the last N turns are pinned; the remaining budget is
filled with the most relevant older turns. This keeps the "needle in the middle" (an order id from turn 9)
when the final question refers back to it.

## TOON

`distillr/core/toon.py` implements the public TOON shape: `key: value`, `key[N]: a,b,c` for primitive arrays,
`key[N]{f1,f2}:` plus one row per line for uniform arrays of flat objects, and a `- ` list for mixed arrays.
Strings are quoted only when ambiguous. A decoder round-trips everything, and the test suite proves it on
nested, mixed, unicode and delimiter-containing data. If the upstream spec moves, this file is the only
place that changes.

## Audit survivability

Every removal keeps a `preview`. `check_answer(answer, manifest, kept_text)` extracts distinctive tokens
(identifiers, numbers, uncommon words) from each preview and flags any that appear in the answer but not in
the text the model actually received. Risk is `high` for paths that look like ids, amounts, dates or
contact fields, `medium` for whole items and truncations, `low` for empty-field and duplicate removals.

This is a heuristic, not a proof. It catches the common failure (the model "remembers" a row we cut, or
hallucinates one that looks like it) and gives the dashboard a trend line. Phase 1 can add an LLM-judge
mode that asks whether the answer needed any removed item.

## What Phase 0 deliberately skips

- Stage 2 (LLMLingua-2) is wired but optional: it needs torch and a 560M-parameter model, and the spec says
  to validate the cheap stages first.
- No proxy, no dashboard, no billing. `docs/spec.md` has the order.
