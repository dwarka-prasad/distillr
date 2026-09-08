"""Stage 1: retrieval / trim.

Decides *what* to send. Structural cleanup (empty fields, duplicates, field allow/deny lists, long-string
truncation) plus relevance ranking with BM25 when a query is given. For chat history it keeps system
messages and the most recent turns, then fills remaining budget with the most relevant older turns.
Everything removed is recorded as a Removal.
"""

from __future__ import annotations

import fnmatch
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from ..payload import chunk_text
from .base import Context, Removal, StageReport, preview

_WORD = re.compile(r"[A-Za-z0-9_@.\-]+")
STOP = frozenset(
    "the a an and or of to in on for with is are was were be been by at from as it this that these those "
    "i you he she we they me my your our their not no yes do does did have has had will would can could "
    "about into over under than then there here what which who whom when where why how all any some".split()
)


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text) if w.lower() not in STOP and len(w) > 1]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = docs
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: list[str], i: int) -> float:
        d = self.docs[i]
        if not d:
            return 0.0
        tf = Counter(d)
        s = 0.0
        for t in query:
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
        return s


@dataclass
class RetrieveStage:
    """Configuration is deliberately explicit; every knob maps to a Removal reason."""

    query: str | None = None
    top_k: int | None = None  # keep the k most relevant items (needs query) or first k (no query)
    min_score: float | None = None  # drop items scoring below this (needs query)
    keep_fields: list[str] | None = None  # glob allowlist on field names, e.g. ["id", "name", "*_at"]
    drop_fields: list[str] | None = None  # glob denylist
    drop_empty: bool = True  # null, "", [], {}
    dedupe: bool = True
    max_string_chars: int | None = None  # truncate long strings with a marker
    keep_last_messages: int | None = None  # chat: always keep the last N turns
    keep_system: bool = True  # chat: always keep system messages
    scorer: Callable[[str, list[str]], list[float]] | None = None  # optional embedding-based ranker
    name: str = field(default="retrieve", init=False)

    def run(self, data: Any, ctx: Context) -> tuple[Any, StageReport]:
        before = ctx.tokens(data)
        removals: list[Removal] = []
        query = self.query or ctx.query

        if isinstance(data, dict) and ctx.kind == "chat":
            inner, report = self._run_list(data["messages"], ctx, query, "chat", removals)
            out: Any = {**data, "messages": inner}
        elif isinstance(data, list):
            out, _ = self._run_list(data, ctx, query, ctx.kind, removals)
        elif isinstance(data, dict):
            out = self._clean_value(data, "$", removals, ctx)
        else:
            out = data
        after = ctx.tokens(out)
        meta = {"query": query, "top_k": self.top_k, "kept": _len(out), "input": _len(data)}
        return out, StageReport(self.name, before, after, removals, meta)

    # ---- lists (tabular / chunks / chat) -------------------------------------------------------
    def _run_list(self, items: list, ctx: Context, query: str | None, kind: str, removals: list[Removal]):
        root = "messages" if kind == "chat" else "rows"
        # 1. field-level cleanup. For lists of records, empty values are removed column-wise (only when the
        #    field is empty in every row) so rows stay uniform and the encoder can use the tabular form;
        #    per-cell removal would save a few "null" tokens and cost the whole table layout.
        items = self._drop_empty_columns(items, root, removals, ctx)
        cleaned = [self._clean_value(it, f"{root}[{i}]", removals, ctx, drop_empty=False) for i, it in enumerate(items)]
        keep = [True] * len(cleaned)

        # 2. dedupe identical items
        if self.dedupe:
            seen: set[str] = set()
            for i, it in enumerate(cleaned):
                key = _canon(it)
                if key in seen:
                    keep[i] = False
                    removals.append(Removal(self.name, "dedupe", f"{root}[{i}]", "duplicate item", preview(it), ctx.tokens(it)))
                seen.add(key)

        # 3. relevance / recency selection
        pinned = set()
        if kind == "chat":
            if self.keep_system:
                pinned |= {i for i, m in enumerate(cleaned) if isinstance(m, dict) and m.get("role") == "system"}
            if self.keep_last_messages:
                pinned |= set(range(max(0, len(cleaned) - self.keep_last_messages), len(cleaned)))
        candidates = [i for i in range(len(cleaned)) if keep[i] and i not in pinned]

        if query and candidates:
            scores = self._scores(query, [cleaned[i] for i in candidates])
            ranked = sorted(zip(candidates, scores), key=lambda p: p[1], reverse=True)
            budget = None if self.top_k is None else max(0, self.top_k - len([i for i in pinned if keep[i]]))
            chosen = set()
            for rank, (i, s) in enumerate(ranked):
                if self.min_score is not None and s < self.min_score:
                    continue
                if budget is not None and rank >= budget:
                    continue
                chosen.add(i)
            for i, s in ranked:
                if i not in chosen:
                    keep[i] = False
                    removals.append(
                        Removal(
                            self.name, "item", f"{root}[{i}]", f"low relevance (score {s:.2f})", preview(cleaned[i]), ctx.tokens(cleaned[i])
                        )
                    )
        elif self.top_k is not None:
            # no query: keep the first k for tables/chunks, the last k for chat
            order = candidates if kind != "chat" else list(reversed(candidates))
            for i in order[max(0, self.top_k - len(pinned)) :]:
                keep[i] = False
                removals.append(
                    Removal(self.name, "item", f"{root}[{i}]", f"beyond top_k={self.top_k}", preview(cleaned[i]), ctx.tokens(cleaned[i]))
                )

        out = [it for i, it in enumerate(cleaned) if keep[i]]
        return out, None

    def _scores(self, query: str, items: list) -> list[float]:
        texts = [chunk_text(it) for it in items]
        if self.scorer is not None:
            return list(self.scorer(query, texts))
        docs = [tokenize(t) for t in texts]
        bm = BM25(docs)
        q = tokenize(query)
        return [bm.score(q, i) for i in range(len(docs))]

    # ---- values ------------------------------------------------------------------------------
    def _drop_empty_columns(self, items: list, root: str, removals: list[Removal], ctx: Context) -> list:
        if not self.drop_empty or not items or not all(isinstance(it, dict) for it in items):
            return items
        paths: dict[tuple, int] = {}  # dotted path -> count of non-empty occurrences
        for it in items:
            for path, v in _leaf_items(it):
                paths[path] = paths.get(path, 0) + (0 if _is_empty(v) else 1)
        dead = [pth for pth, n in paths.items() if n == 0]
        if not dead:
            return items
        for pth in dead:
            removals.append(Removal(self.name, "field", f"{root}[*].{'.'.join(pth)}", "empty in every row", "", len(items)))
        return [_without(it, dead) for it in items]

    def _clean_value(self, value: Any, path: str, removals: list[Removal], ctx: Context, drop_empty: bool | None = None) -> Any:
        de = self.drop_empty if drop_empty is None else drop_empty
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                p = f"{path}.{k}"
                if self.keep_fields and not any(fnmatch.fnmatch(k, g) for g in self.keep_fields):
                    removals.append(Removal(self.name, "field", p, "not in keep_fields", preview(v), ctx.tokens(v)))
                    continue
                if self.drop_fields and any(fnmatch.fnmatch(k, g) for g in self.drop_fields):
                    removals.append(Removal(self.name, "field", p, "in drop_fields", preview(v), ctx.tokens(v)))
                    continue
                if de and _is_empty(v):
                    removals.append(Removal(self.name, "field", p, "empty value", preview(v), 1))
                    continue
                out[k] = self._clean_value(v, p, removals, ctx, drop_empty)
            return out
        if isinstance(value, list):
            if value and all(isinstance(x, dict) for x in value):
                # nested list of records: same column-wise rule as top-level lists, keep rows uniform
                value = self._drop_empty_columns(value, path, removals, ctx)
                return [self._clean_value(v, f"{path}[{i}]", removals, ctx, False) for i, v in enumerate(value)]
            return [self._clean_value(v, f"{path}[{i}]", removals, ctx, drop_empty) for i, v in enumerate(value)]
        if isinstance(value, str) and self.max_string_chars and len(value) > self.max_string_chars:
            cut = value[self.max_string_chars :]
            removals.append(
                Removal(self.name, "truncation", path, f"string over {self.max_string_chars} chars", preview(cut), ctx.counter.count(cut))
            )
            return value[: self.max_string_chars] + "…"
        return value


def _is_empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _leaf_items(obj: dict, prefix: tuple = ()) -> list[tuple[tuple, Any]]:
    """(dotted-path, value) for every leaf of a record. Nested dicts descend; lists are leaves."""
    out: list[tuple[tuple, Any]] = []
    for k, v in obj.items():
        if isinstance(v, dict) and v:
            out.extend(_leaf_items(v, prefix + (k,)))
        else:
            out.append((prefix + (k,), v))
    return out


def _without(obj: dict, dead: list[tuple]) -> dict:
    out: dict = {}
    for k, v in obj.items():
        here = [d for d in dead if d and d[0] == k]
        if any(len(d) == 1 for d in here):
            continue
        if isinstance(v, dict) and v and here:
            v = _without(v, [d[1:] for d in here if len(d) > 1])
        out[k] = v
    return out


def _canon(v: Any) -> str:
    import json

    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def _len(v: Any) -> int | None:
    if isinstance(v, list):
        return len(v)
    if isinstance(v, dict) and isinstance(v.get("messages"), list):
        return len(v["messages"])
    return None
