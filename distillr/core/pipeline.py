"""Pipeline: composes stages, measures each one, produces a CompressionResult and (optionally) writes
the run to the token ledger."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .payload import Payload, wrap
from .stages import AuditFlag, AuditStage, Context, EncodeStage, Removal, RetrieveStage, StageReport, check_answer
from .tokenizers import TokenCounter, for_encoding, for_model


@dataclass
class CompressionResult:
    id: str
    text: str  # what to send to the model
    encoding: str
    payload_kind: str
    tokens_before: int
    tokens_after: int
    tokenizer: str
    stages: list[StageReport]
    manifest: list[Removal]
    query: str | None = None
    duration_ms: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def savings_pct(self) -> float:
        return 0.0 if self.tokens_before == 0 else 100.0 * self.saved / self.tokens_before

    def check_answer(self, answer: str) -> list[AuditFlag]:
        """Did the model's answer lean on anything we removed?"""
        return check_answer(answer, self.manifest, kept_text=self.text)

    def to_dict(self, include_text: bool = False) -> dict:
        d = {
            "id": self.id,
            "encoding": self.encoding,
            "payload_kind": self.payload_kind,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "saved": self.saved,
            "savings_pct": round(self.savings_pct, 2),
            "tokenizer": self.tokenizer,
            "query": self.query,
            "duration_ms": self.duration_ms,
            "stages": [s.to_dict() for s in self.stages],
            "manifest": [r.to_dict() for r in self.manifest],
        }
        if include_text:
            d["text"] = self.text
        return d


class Pipeline:
    """Default order: retrieve -> (semantic) -> encode -> audit. Pass your own `stages` to change it."""

    def __init__(self, stages: list | None = None, *, tokenizer: str | None = None, model: str | None = None) -> None:
        self.stages = stages if stages is not None else [RetrieveStage(), EncodeStage()]
        self.counter: TokenCounter = for_model(model) if model else for_encoding(tokenizer)

    def run(self, payload: Payload | Any, query: str | None = None) -> CompressionResult:
        p = payload if isinstance(payload, Payload) else wrap(payload)
        t0 = time.perf_counter()
        ctx = Context(self.counter, p.kind, query)
        before = self.counter.count(p.baseline_text)
        data: Any = p.data
        reports: list[StageReport] = []
        manifest: list[Removal] = []
        for stage in self.stages:
            if isinstance(stage, AuditStage):
                data, rep = stage.run(data, ctx, manifest)
            else:
                data, rep = stage.run(data, ctx)
            reports.append(rep)
            manifest.extend(rep.removals)
        if not isinstance(data, str):
            # no encode stage was configured: fall back to compact JSON so the result is sendable
            data = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        encoding = next((r.meta.get("format") for r in reversed(reports) if r.name == "encode"), "json")
        after = self.counter.count(data)
        # Reports measure structured data between stages as pretty JSON; make the first stage start from the
        # true baseline so per-stage numbers add up to the total.
        if reports:
            reports[0].tokens_before = before
        return CompressionResult(
            id=uuid.uuid4().hex[:12],
            text=data,
            encoding=encoding,
            payload_kind=p.kind,
            tokens_before=before,
            tokens_after=after,
            tokenizer=self.counter.label,
            stages=reports,
            manifest=manifest,
            query=query,
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )


def compress(
    payload: Any,
    *,
    query: str | None = None,
    stages: list | None = None,
    encode: str = "auto",
    flatten: bool = False,
    top_k: int | None = None,
    keep_fields: list[str] | None = None,
    drop_fields: list[str] | None = None,
    keep_last_messages: int | None = None,
    max_string_chars: int | None = None,
    tokenizer: str | None = None,
    model: str | None = None,
    ledger: bool = True,
    tag: str | None = None,
) -> CompressionResult:
    """One-call SDK entry point.

    result = distillr.compress(rows, query="orders shipped to Berlin", top_k=20)
    prompt = f"Answer using this data:\\n{result.text}"
    ...
    flags = result.check_answer(model_answer)
    """
    if stages is None:
        stages = [
            RetrieveStage(
                top_k=top_k,
                keep_fields=keep_fields,
                drop_fields=drop_fields,
                keep_last_messages=keep_last_messages,
                max_string_chars=max_string_chars,
            ),
            EncodeStage(format=encode, flatten=flatten),
            AuditStage(),
        ]
    result = Pipeline(stages, tokenizer=tokenizer, model=model).run(payload, query=query)
    if ledger:
        from .ledger import Ledger

        Ledger().record(result, tag=tag)
    return result
