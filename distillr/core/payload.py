"""Payload loading and shape detection.

Distillr treats four shapes differently:
  tabular  - list of dicts sharing most keys (rows, records, API list responses)
  chat     - list of {role, content} messages
  chunks   - list of retrieval chunks (dicts with text/content/page_content, or plain strings)
  object   - a single dict (nested API response, config)
  text     - a plain string
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Kind = str  # "tabular" | "chat" | "chunks" | "object" | "text" | "list"

CHUNK_TEXT_KEYS = ("text", "content", "page_content", "chunk", "body", "passage")


@dataclass
class Payload:
    data: Any
    kind: Kind
    source_text: str | None = None  # the bytes the user would have sent, for an honest baseline
    meta: dict = field(default_factory=dict)

    @property
    def baseline_text(self) -> str:
        """What the team would have pasted into the prompt: the original text if we have it,
        otherwise pretty JSON, which is what most apps do."""
        if self.source_text is not None:
            return self.source_text
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, indent=2, ensure_ascii=False)


def detect_kind(data: Any) -> Kind:
    if isinstance(data, str):
        return "text"
    if isinstance(data, dict):
        # {"messages": [...], ...} is the common chat-completion request wrapper
        msgs = data.get("messages")
        if isinstance(msgs, list) and msgs and _is_chat(msgs):
            return "chat"
        return "object"
    if isinstance(data, list):
        if not data:
            return "list"
        if all(isinstance(x, str) for x in data):
            return "chunks"
        if all(isinstance(x, dict) for x in data):
            if _is_chat(data):
                return "chat"
            if _is_chunks(data):
                return "chunks"
            if _is_tabular(data):
                return "tabular"
        return "list"
    return "object"


def _is_chat(items: list) -> bool:
    return all(isinstance(m, dict) and "role" in m and ("content" in m or "tool_calls" in m) for m in items)


def _is_chunks(items: list) -> bool:
    hits = sum(1 for it in items if any(k in it and isinstance(it[k], str) for k in CHUNK_TEXT_KEYS))
    return hits >= max(1, int(0.8 * len(items)))


def _is_tabular(items: list) -> bool:
    keysets = [frozenset(d.keys()) for d in items]
    union = frozenset().union(*keysets)
    if not union:
        return False
    # rows share at least 60% of the key universe on average
    coverage = sum(len(k) for k in keysets) / (len(keysets) * len(union))
    return coverage >= 0.6


def chunk_text(item: Any) -> str:
    """Extract the searchable text of a chunk / row / message, including nested values."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for k in CHUNK_TEXT_KEYS:
            v = item.get(k)
            if isinstance(v, str):
                return v
            if isinstance(v, list):  # chat content blocks
                return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in v)
        return " ".join(_leaves(item))
    return json.dumps(item, ensure_ascii=False)


def _leaves(v: Any) -> list[str]:
    if isinstance(v, dict):
        return [s for x in v.values() for s in _leaves(x)]
    if isinstance(v, list):
        return [s for x in v for s in _leaves(x)]
    if isinstance(v, bool) or v is None:
        return []
    return [str(v)]


def load(path: str | Path) -> Payload:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix == ".jsonl":
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        return Payload(rows, detect_kind(rows), source_text=raw, meta={"format": "jsonl"})
    if suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(raw)))
        return Payload(rows, "tabular", source_text=raw, meta={"format": "csv"})
    if suffix in (".json",):
        data = json.loads(raw)
        return Payload(data, detect_kind(data), source_text=raw, meta={"format": "json"})
    # try JSON anyway, else treat as text
    try:
        data = json.loads(raw)
        return Payload(data, detect_kind(data), source_text=raw, meta={"format": "json"})
    except json.JSONDecodeError:
        return Payload(raw, "text", source_text=raw, meta={"format": "text"})


def wrap(data: Any) -> Payload:
    """Wrap an in-memory object (SDK use)."""
    return Payload(data, detect_kind(data))
