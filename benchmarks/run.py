"""Phase 0 benchmark: token savings per stage and needle recall on five payload types.

Success gate (from the spec): a believable 50-70%+ reduction on real data without hurting the downstream
task. We approximate "downstream task" with needle recall: every fact the question needs must survive
compression verbatim in the text we would send to the model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from distillr.core import AuditStage, EncodeStage, Pipeline, RetrieveStage, load  # noqa: E402

PAYLOADS = HERE / "payloads"


def recall(text: str, needles: list[str]) -> float:
    low = text.lower()
    return sum(1 for n in needles if n.lower() in low) / len(needles)


def run_case(name: str, spec: dict, encoding: str, tokenizer: str, flatten: bool = False) -> dict:
    payload = load(PAYLOADS / spec["file"])
    stages = [
        RetrieveStage(
            query=spec.get("query"), top_k=spec.get("top_k"), keep_last_messages=spec.get("keep_last"), drop_fields=spec.get("drop_fields")
        ),
        EncodeStage(format=encoding, flatten=flatten),
        AuditStage(),
    ]
    r = Pipeline(stages, tokenizer=tokenizer).run(payload, query=spec.get("query"))
    encode_only = Pipeline([EncodeStage(format=encoding, flatten=flatten)], tokenizer=tokenizer).run(payload)
    retrieve = next(s for s in r.stages if s.name == "retrieve")
    encode = next(s for s in r.stages if s.name == "encode")
    return {
        "case": name,
        "kind": payload.kind,
        "encoding": encoding,
        "tokens_before": r.tokens_before,
        "after_retrieve": retrieve.tokens_after,
        "tokens_after": r.tokens_after,
        "savings_pct": round(r.savings_pct, 1),
        "retrieve_pct": round(retrieve.savings_pct, 1),
        "encode_pct": round(encode.savings_pct, 1),
        "chosen": encode.meta.get("format"),
        "encode_only_pct": round(encode_only.savings_pct, 1),
        "encode_only_chosen": encode_only.stages[0].meta.get("format"),
        "recall": recall(r.text, spec["needles"]),
        "removals": len(r.manifest),
        "ms": r.duration_ms,
    }


def main(write: bool = True, tokenizer: str = "o200k_base") -> list[dict]:
    if not (PAYLOADS / "cases.json").exists():
        sys.path.insert(0, str(HERE))
        import generate

        generate.main()
    cases = json.loads((PAYLOADS / "cases.json").read_text())
    rows = []
    for name, spec in cases.items():
        for enc in ("auto", "toon", "json", "csv"):
            rows.append(run_case(name, spec, enc, tokenizer, flatten=bool(spec.get("flatten"))))

    best = [r for r in rows if r["encoding"] == "auto"]
    total_before = sum(r["tokens_before"] for r in best)
    total_after = sum(r["tokens_after"] for r in best)
    overall = 100 * (total_before - total_after) / total_before
    min_recall = min(r["recall"] for r in best)

    lines = [
        "# Phase 0 benchmark results",
        "",
        f"Tokenizer: `{tokenizer}` (tiktoken). Baseline is the payload exactly as a team would paste it (pretty JSON / JSONL). ",
        "Retrieve = Stage 1 (structural trim + BM25 ranking with the case's query). Encode = Stage 3 (lossless re-serialization). ",
        "Recall = fraction of the facts the downstream question needs that survive verbatim in the compressed text.",
        "",
        "## Pipeline (retrieve + auto encode)",
        "",
        "| Case | Kind | Tokens before | After retrieve | After encode | Retrieve % | Encode % (format) | **Total saved** | Needle recall | Removals |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in best:
        lines.append(
            f"| {r['case']} | {r['kind']} | {r['tokens_before']:,} | {r['after_retrieve']:,} | {r['tokens_after']:,} | {r['retrieve_pct']}% | {r['encode_pct']}% ({r['chosen']}) | **{r['savings_pct']}%** | {r['recall']:.0%} | {r['removals']} |"
        )
    lines += [
        "",
        f"**Overall: {total_before:,} -> {total_after:,} tokens, {overall:.1f}% saved, minimum needle recall {min_recall:.0%}.**",
        "",
        "## Format layer alone (no trimming; flatten where the case enables it)",
        "",
        "| Case | auto | TOON | compact JSON | CSV |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in cases:
        by = {r["encoding"]: r for r in rows if r["case"] == name}
        lines.append(
            f"| {name} | {by['auto']['encode_only_pct']}% ({by['auto']['encode_only_chosen']}) | {by['toon']['encode_only_pct']}% | {by['json']['encode_only_pct']}% | {by['csv']['encode_only_pct']}% |"
        )
    gate = overall >= 50 and min_recall >= 1.0
    lines += [
        "",
        "## Success gate",
        "",
        f"Target: 50-70%+ reduction with no needle loss. Result: **{'PASS' if gate else 'FAIL'}** ({overall:.1f}% saved, recall {min_recall:.0%}).",
        "",
        "Regenerate with `python benchmarks/generate.py && distillr bench`.",
    ]
    text = "\n".join(lines) + "\n"
    print(text)
    if write:
        (HERE / "RESULTS.md").write_text(text)
    return rows


if __name__ == "__main__":
    main(write="--no-write" not in sys.argv)
