import json

import pytest

from distillr.core import toon

CASES = [
    {"a": 1, "b": "two", "c": True, "d": None, "e": 3.5},
    {"users": [{"id": 1, "name": "Ada", "admin": True}, {"id": 2, "name": "Grace", "admin": False}]},
    {"tags": ["x", "y", "z"], "empty": [], "nested": {"deep": {"k": "v"}}},
    [{"id": 1, "v": "a,b"}, {"id": 2, "v": "needs: quote"}, {"id": 3, "v": " lead"}],
    {"mixed": [1, "two", None, {"k": 1}]},
    {"list_of_lists": [[1, 2], [3, 4]]},
    {"s": "123", "t": "true", "u": "", "v": 'with "quotes" inside'},
    {"rows": [{"a": {"nested": 1}, "b": 2}, {"a": {"nested": 3}, "b": 4}]},
    {"messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi: how are you?"}]},
    {"unicode": "héllo wörld ✓", "emoji": "🐦"},
    {"weird key": 1, "k:v": 2, "k,v": 3},
    [],
    [1, 2, 3],
    "just a string",
    42,
]


@pytest.mark.parametrize("data", CASES, ids=[str(i) for i in range(len(CASES))])
def test_roundtrip(data):
    text = toon.encode(data)
    assert toon.decode(text) == data, text


def test_tabular_form_is_used_for_uniform_rows():
    text = toon.encode({"rows": [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]})
    assert text.splitlines()[0] == "rows[2]{id,name}:"
    assert text.splitlines()[1] == "  1,Ada"


def test_toon_is_shorter_than_json_for_tables():
    rows = [{"order_id": f"ORD-{i}", "status": "shipped", "total_usd": i * 1.5, "city": "Berlin"} for i in range(50)]
    assert len(toon.encode(rows)) < len(json.dumps(rows, separators=(",", ":"))) * 0.7


def test_alternate_delimiter():
    data = [{"a": "x,y", "b": 1}]
    text = toon.encode(data, delimiter="\t")
    assert "\t" in text and toon.decode(text, delimiter="\t") == data
