"""Stage 3: format encoding. Lossless re-serialization into a token-efficient shape.

Formats: toon (default), json (minified), csv (tabular only, falls back to toon), yaml-lite (toon
without array headers is close enough that we do not ship a separate YAML encoder).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any

from .. import toon
from .base import Context, StageReport

FORMATS = ("auto", "toon", "json", "csv")


@dataclass
class EncodeStage:
    """`auto` encodes with every candidate and keeps the one with the fewest tokens on the active tokenizer.
    `flatten` turns nested objects inside list items into dotted keys (customer.name) so more arrays qualify
    for TOON's tabular form; `decode` reverses it."""

    format: str = "auto"
    delimiter: str = ","
    flatten: bool = False
    name: str = field(default="encode", init=False)

    def run(self, data: Any, ctx: Context) -> tuple[str, StageReport]:
        before = ctx.tokens(data)
        meta: dict = {"lossless": True}
        if isinstance(data, str):
            return data, StageReport(self.name, before, ctx.counter.count(data), [], {"format": "text", **meta})
        if self.flatten:
            data = flatten(data)
            meta["flattened"] = True
        candidates = [self.format] if self.format != "auto" else ["toon", "json", "csv"]
        best: tuple[int, str, str] | None = None
        tried: dict[str, int] = {}
        for fmt in candidates:
            if fmt == "csv" and not _flat_rows(data):
                if self.format == "csv":
                    fmt = "toon"  # not tabular: fall back
                else:
                    continue
            text = _encode(data, fmt, self.delimiter)
            n = ctx.counter.count(text)
            tried[fmt] = n
            if best is None or n < best[0]:
                best = (n, fmt, text)
        assert best is not None
        after, fmt, text = best
        meta["format"] = fmt
        if self.format == "auto":
            meta["candidates"] = tried
        return text, StageReport(self.name, before, after, [], meta)


def _encode(data: Any, fmt: str, delimiter: str) -> str:
    if fmt == "json":
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if fmt == "csv":
        return _csv(data)
    return toon.encode(data, delimiter)


SEP = "."


def flatten(data: Any) -> Any:
    """Flatten nested dicts inside list items into dotted keys. Lists stay lists."""
    if isinstance(data, list):
        return [_flatten_obj(x) if isinstance(x, dict) else flatten(x) for x in data]
    if isinstance(data, dict):
        return {k: flatten(v) if isinstance(v, list) else v for k, v in data.items()}
    return data


def _flatten_obj(obj: dict, prefix: str = "") -> dict:
    out: dict = {}
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            out.update(_flatten_obj(v, key + SEP))
        elif isinstance(v, list):
            out[key] = flatten(v)
        else:
            out[key] = v
    return out


def unflatten(data: Any) -> Any:
    if isinstance(data, list):
        return [unflatten(x) for x in data]
    if isinstance(data, dict):
        out: dict = {}
        for k, v in data.items():
            parts = k.split(SEP) if isinstance(k, str) else [k]
            cur = out
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = unflatten(v)
        return out
    return data


def _flat_rows(data: Any) -> bool:
    return (
        isinstance(data, list)
        and bool(data)
        and all(isinstance(r, dict) and all(v is None or isinstance(v, (str, int, float, bool)) for v in r.values()) for r in data)
    )


def _csv(rows: list[dict]) -> str:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    return buf.getvalue().rstrip("\n")


def decode(text: str, fmt: str, flattened: bool = False) -> Any:
    if fmt == "json":
        data = json.loads(text)
    elif fmt == "csv":
        data = list(csv.DictReader(io.StringIO(text)))
    else:
        data = toon.decode(text)
    return unflatten(data) if flattened else data
