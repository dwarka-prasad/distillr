# Changelog

## 0.1.0 - 2026-09-09 (Phase 0)

- Core engine with the four-stage contract; Stage 1 retrieve/trim and Stage 3 encode complete
- TOON encoder and decoder (lossless), compact JSON, CSV; `auto` picks the cheapest on the real tokenizer;
  `flatten` for nested objects
- Column-wise empty-field removal, dedupe, field globs, truncation, BM25 ranking, chat-aware pinning
- Stage 2 (LLMLingua-2, optional extra) and Stage 4 (audit manifest, `check_answer`) interfaces
- Token ledger on SQLite; `distillr ledger`
- CLI: analyze, encode, decode, ledger, bench; SDK: `distillr.compress`
- Benchmarks on five payload types: 95.2% saved, 100% needle recall
