"""Stage contract. Every stage is a pure function from data to (data, report) and must record what it
removed so the audit stage can later tell whether a model answer leaned on something that was cut."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from ..tokenizers import TokenCounter


@dataclass
class Removal:
    """One thing a stage took out of the payload."""

    stage: str
    kind: str  # item | field | truncation | dedupe | tokens
    path: str  # JSONPath-ish location, e.g. rows[17] or rows[3].notes
    reason: str
    preview: str  # short text of what was removed, used by the audit checker
    tokens: int = 0  # approximate tokens the removal saved

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StageReport:
    name: str
    tokens_before: int
    tokens_after: int
    removals: list[Removal] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def savings_pct(self) -> float:
        return 0.0 if self.tokens_before == 0 else 100.0 * self.saved / self.tokens_before

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "saved": self.saved,
            "savings_pct": round(self.savings_pct, 2),
            "removals": len(self.removals),
            "meta": self.meta,
        }


@dataclass
class Context:
    counter: TokenCounter
    kind: str
    query: str | None = None

    def render(self, data: Any) -> str:
        """Canonical text for measuring structured data between stages (pretty JSON, what apps send)."""
        if isinstance(data, str):
            return data
        return json.dumps(data, indent=2, ensure_ascii=False)

    def tokens(self, data: Any) -> int:
        return self.counter.count(self.render(data))


class Stage(Protocol):
    name: str

    def run(self, data: Any, ctx: Context) -> tuple[Any, StageReport]: ...


def preview(value: Any, limit: int = 120) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[: limit - 1] + "…"
