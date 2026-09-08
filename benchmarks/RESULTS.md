# Phase 0 benchmark results

Tokenizer: `o200k_base` (tiktoken). Baseline is the payload exactly as a team would paste it (pretty JSON / JSONL). 
Retrieve = Stage 1 (structural trim + BM25 ranking with the case's query). Encode = Stage 3 (lossless re-serialization). 
Recall = fraction of the facts the downstream question needs that survive verbatim in the compressed text.

## Pipeline (retrieve + auto encode)

| Case | Kind | Tokens before | After retrieve | After encode | Retrieve % | Encode % (format) | **Total saved** | Needle recall | Removals |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| orders | tabular | 47,352 | 2,828 | 1,795 | 94.0% | 36.5% (json) | **96.2%** | 100% | 190 |
| chat | chat | 5,301 | 507 | 337 | 90.4% | 33.5% (toon) | **93.6%** | 100% | 112 |
| rag_chunks | chunks | 4,622 | 554 | 409 | 88.0% | 26.2% (json) | **91.2%** | 100% | 36 |
| api_object | object | 9,334 | 4,157 | 2,018 | 55.5% | 51.5% (toon) | **78.4%** | 100% | 252 |
| logs | tabular | 36,379 | 761 | 388 | 97.9% | 49.0% (csv) | **98.9%** | 100% | 394 |

**Overall: 102,988 -> 4,947 tokens, 95.2% saved, minimum needle recall 100%.**

## Format layer alone (no trimming; flatten where the case enables it)

| Case | auto | TOON | compact JSON | CSV |
|---|---:|---:|---:|---:|
| orders | 35.9% (json) | 30.6% | 35.9% | 30.6% |
| chat | 27.3% (json) | 16.5% | 27.3% | 16.5% |
| rag_chunks | 26.8% (json) | 15.6% | 26.8% | 15.6% |
| api_object | 59.2% (toon) | 59.2% | 31.3% | 59.2% |
| logs | 19.8% (json) | 5.2% | 19.8% | 5.2% |

## Success gate

Target: 50-70%+ reduction with no needle loss. Result: **PASS** (95.2% saved, recall 100%).

Regenerate with `python benchmarks/generate.py && distillr bench`.
