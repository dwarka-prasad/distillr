"""Stage 4: audit tagger.

Collects every Removal produced by earlier stages into a manifest and scores the risk of each. After
the model answers, `check_answer` looks for distinctive tokens from removed content in the answer:
if the model "used" something we cut, the compression was not safe for that request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .base import Context, Removal, StageReport

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{4,}|\d[\d.,\-]{2,}|[A-Z]{2,}[0-9\-]+")
_COMMON = frozenset(
    "about above after again against being below between could every first found great little never other "
    "people place right should small still their there these thing think three through under until where "
    "which while would years string number value order status total items count error message null false true "
    "created updated deleted name email phone address".split()
)
HIGH_RISK_HINTS = ("id", "amount", "total", "price", "date", "email", "phone", "address", "status", "error")


@dataclass
class AuditFlag:
    path: str
    stage: str
    matched: str
    reason: str
    risk: str  # low | medium | high

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def risk_of(r: Removal) -> str:
    p = r.path.lower()
    if r.kind == "dedupe":
        return "low"
    if r.kind == "field" and r.reason == "empty value":
        return "low"
    if any(h in p for h in HIGH_RISK_HINTS):
        return "high"
    if r.kind in ("item", "tokens", "truncation"):
        return "medium"
    return "low"


def distinctive_tokens(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text):
        lw = w.lower().strip(".,-")
        if lw and lw not in _COMMON and not lw.startswith(("http", "www")):
            out.add(lw)
    return out


def check_answer(answer: str, manifest: list[Removal], kept_text: str | None = None) -> list[AuditFlag]:
    """Flag removals whose distinctive content shows up in the model's answer.

    Tokens that also occur in `kept_text` (what the model actually received) are not evidence of leakage:
    the model could have read them from the compressed payload."""
    if not answer or not manifest:
        return []
    ans = set(distinctive_tokens(answer))
    if kept_text:
        ans -= distinctive_tokens(kept_text)
        kept_low = kept_text.lower()
    else:
        kept_low = ""
    # also allow substring match for identifiers like ORD-1042
    flags: list[AuditFlag] = []
    for r in manifest:
        if r.kind == "field" and r.reason == "empty value":
            continue  # nothing to leak from an empty value
        toks = distinctive_tokens(r.preview)
        hit = next((t for t in toks if t in ans), None)
        if hit is None:
            ids = [t for t in toks if re.search(r"\d", t) and t not in kept_low]
            hit = next((t for t in ids if t in answer.lower()), None)
        if hit:
            flags.append(AuditFlag(r.path, r.stage, hit, r.reason, risk_of(r)))
    return flags


@dataclass
class AuditStage:
    """Summarizes the manifest; does not change data."""

    name: str = field(default="audit", init=False)

    def run(self, data: Any, ctx: Context, manifest: list[Removal] | None = None) -> tuple[Any, StageReport]:
        manifest = manifest or []
        t = ctx.counter.count(data) if isinstance(data, str) else ctx.tokens(data)
        by_risk = {"high": 0, "medium": 0, "low": 0}
        for r in manifest:
            by_risk[risk_of(r)] += 1
        meta = {"removals": len(manifest), "by_risk": by_risk, "tokens_removed": sum(r.tokens for r in manifest)}
        return data, StageReport(self.name, t, t, [], meta)
