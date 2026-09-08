"""TOON (Token-Oriented Object Notation) encoder and decoder.

Follows the public TOON format: indentation for nesting, `key: value` for scalars, `key[N]: a,b,c` for
primitive arrays, and the tabular form `key[N]{f1,f2}:` followed by one comma-separated row per line for
arrays of uniform objects. Non-uniform arrays fall back to a `- ` list. Strings are quoted only when they
would otherwise be ambiguous. The encoder is lossless for JSON data; `decode` round-trips it.
"""

from __future__ import annotations

import json
import re
from typing import Any

INDENT = "  "
_NEEDS_QUOTE = re.compile(r'^\s|\s$|[,:\[\]{}"\n\r\t#]|^-\s|^$')
_LOOKS_SCALAR = re.compile(r"^(true|false|null|-?\d+(\.\d+)?([eE][-+]?\d+)?)$")


# ------------------------------------------------------------------ encode
def encode(data: Any, delimiter: str = ",") -> str:
    lines: list[str] = []
    if isinstance(data, list):
        _encode_array(None, data, lines, 0, delimiter)
    elif isinstance(data, dict):
        _encode_object(data, lines, 0, delimiter)
    else:
        lines.append(_scalar(data, delimiter))
    return "\n".join(lines)


def _encode_object(obj: dict, lines: list[str], depth: int, d: str) -> None:
    pad = INDENT * depth
    for k, v in obj.items():
        key = _key(k)
        if isinstance(v, dict):
            if not v:
                lines.append(f"{pad}{key}: {{}}")
            else:
                lines.append(f"{pad}{key}:")
                _encode_object(v, lines, depth + 1, d)
        elif isinstance(v, list):
            _encode_array(key, v, lines, depth, d)
        else:
            lines.append(f"{pad}{key}: {_scalar(v, d)}")


def _encode_array(key: str | None, arr: list, lines: list[str], depth: int, d: str) -> None:
    pad = INDENT * depth
    head = f"{key}" if key is not None else ""
    n = len(arr)
    if n == 0:
        lines.append(f"{pad}{head}[0]:")
        return
    if all(_is_scalar(x) for x in arr):
        lines.append(f"{pad}{head}[{n}]: " + d.join(_scalar(x, d) for x in arr))
        return
    fields = _tabular_fields(arr)
    if fields is not None:
        lines.append(f"{pad}{head}[{n}]{{{d.join(_key(f) for f in fields)}}}:")
        for row in arr:
            lines.append(pad + INDENT + d.join(_scalar(row.get(f), d) for f in fields))
        return
    # mixed / nested: list form
    lines.append(f"{pad}{head}[{n}]:")
    for item in arr:
        if isinstance(item, dict) and item:
            sub: list[str] = []
            _encode_object(item, sub, 0, d)
            lines.append(f"{pad}{INDENT}- {sub[0].lstrip()}")
            for extra in sub[1:]:
                lines.append(f"{pad}{INDENT}  {extra}")
        elif isinstance(item, list):
            sub = []
            _encode_array(None, item, sub, 0, d)
            lines.append(f"{pad}{INDENT}- {sub[0]}")
            for extra in sub[1:]:
                lines.append(f"{pad}{INDENT}  {extra}")
        else:
            lines.append(f"{pad}{INDENT}- {_scalar(item, d)}")


def _tabular_fields(arr: list) -> list[str] | None:
    """Uniform arrays of flat objects (all-scalar values, same keys) get the tabular form."""
    if not all(isinstance(x, dict) and x for x in arr):
        return None
    first = list(arr[0].keys())
    for x in arr:
        if list(x.keys()) != first:
            return None
        if not all(_is_scalar(v) for v in x.values()):
            return None
    return first


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _key(k: str) -> str:
    return _quote(str(k)) if _NEEDS_QUOTE.search(str(k)) else str(k)


def _scalar(v: Any, d: str) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return json.dumps(v)
    s = str(v)
    if _NEEDS_QUOTE.search(s) or _LOOKS_SCALAR.match(s) or (d != "," and d in s):
        return _quote(s)
    return s


def _quote(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


# ------------------------------------------------------------------ decode
class _Lines:
    def __init__(self, text: str) -> None:
        self.items = [(len(ln) - len(ln.lstrip(" ")), ln.strip()) for ln in text.splitlines() if ln.strip()]
        self.i = 0

    def peek(self):
        return self.items[self.i] if self.i < len(self.items) else None

    def next(self):
        it = self.items[self.i]
        self.i += 1
        return it


_ARRAY_HEAD = re.compile(r'^(?P<key>"(?:[^"\\]|\\.)*"|[^\[\]{}:]*)\[(?P<n>\d+)\](?:\{(?P<fields>[^}]*)\})?:\s*(?P<rest>.*)$')
_KV = re.compile(r'^(?P<key>"(?:[^"\\]|\\.)*"|[^:]+?):\s*(?P<rest>.*)$')


def decode(text: str, delimiter: str = ",") -> Any:
    ls = _Lines(text)
    first = ls.peek()
    if first is None:
        return None
    if _ARRAY_HEAD.match(first[1]) and _ARRAY_HEAD.match(first[1]).group("key") == "":
        return _parse_array(ls, first[0], delimiter)
    if _KV.match(first[1]) or _ARRAY_HEAD.match(first[1]):
        return _parse_object(ls, first[0], delimiter)
    return _parse_scalar(first[1])


def _parse_object(ls: _Lines, depth: int, d: str) -> dict:
    obj: dict = {}
    while (cur := ls.peek()) is not None and cur[0] == depth:
        indent, line = cur
        m = _ARRAY_HEAD.match(line)
        if m and m.group("key") != "":
            key = _unkey(m.group("key"))
            obj[key] = _parse_array(ls, depth, d)
            continue
        m = _KV.match(line)
        if not m:
            break
        ls.next()
        key, rest = _unkey(m.group("key")), m.group("rest")
        if rest == "":
            nxt = ls.peek()
            obj[key] = _parse_object(ls, nxt[0], d) if nxt and nxt[0] > depth else ""
        elif rest == "{}":
            obj[key] = {}
        else:
            obj[key] = _parse_scalar(rest)
    return obj


def _parse_array(ls: _Lines, depth: int, d: str) -> list:
    indent, line = ls.next()
    m = _ARRAY_HEAD.match(line)
    n, fields, rest = int(m.group("n")), m.group("fields"), m.group("rest")
    if n == 0:
        return []
    if fields is not None:
        names = [_unkey(f) for f in _split(fields, d)]
        rows = []
        for _ in range(n):
            _, row = ls.next()
            rows.append(dict(zip(names, (_parse_scalar(c) for c in _split(row, d)))))
        return rows
    if rest:
        return [_parse_scalar(c) for c in _split(rest, d)]
    items = []
    for _ in range(n):
        ind, body = ls.next()
        assert body.startswith("- "), f"expected list item, got {body!r}"
        body = body[2:]
        am = _ARRAY_HEAD.match(body)
        if am and am.group("key") == "":
            # nested array as a list item: re-inject the line for the array parser
            ls.i -= 1
            ls.items[ls.i] = (ind + 2, body)
            items.append(_parse_array(ls, ind + 2, d))
            continue
        km = _KV.match(body) or am
        if km:
            # object item: first pair inline, further pairs indented by 2 under the dash
            ls.i -= 1
            ls.items[ls.i] = (ind + 2, body)
            items.append(_parse_object(ls, ind + 2, d))
        else:
            items.append(_parse_scalar(body))
    return items


def _split(s: str, d: str) -> list[str]:
    out, cur, q, i = [], "", False, 0
    while i < len(s):
        c = s[i]
        if c == '"':
            q = not q
            cur += c
        elif c == "\\" and q and i + 1 < len(s):
            cur += c + s[i + 1]
            i += 1
        elif c == d and not q:
            out.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur)
    return [x.strip() for x in out]


def _parse_scalar(s: str) -> Any:
    s = s.strip()
    if s.startswith('"'):
        return json.loads(s)
    if s == "null":
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    if _LOOKS_SCALAR.match(s):
        return json.loads(s)
    return s


def _unkey(k: str) -> str:
    k = k.strip()
    return json.loads(k) if k.startswith('"') else k
