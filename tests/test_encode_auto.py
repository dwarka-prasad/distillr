from distillr.core import EncodeStage, detect_kind
from distillr.core.payload import chunk_text
from distillr.core.stages.base import Context
from distillr.core.stages.encode import decode, flatten, unflatten
from distillr.core.tokenizers import TokenCounter

NESTED = [
    {"order_id": f"ORD-{i}", "customer": {"name": "Ada" if i == 3 else f"Cust {i}", "city": "Berlin"}, "total": i * 2.5} for i in range(20)
]


def ctx():
    return Context(TokenCounter(), "tabular")


def test_chunk_text_includes_nested_values():
    assert "Ada" in chunk_text(NESTED[3])
    assert "Berlin" in chunk_text(NESTED[0])


def test_chat_wrapper_detected_with_extra_keys():
    data = {"model": "gpt-4o", "temperature": 0.2, "metadata": {"a": 1}, "messages": [{"role": "user", "content": "hi"}]}
    assert detect_kind(data) == "chat"


def test_flatten_roundtrip():
    flat = flatten(NESTED)
    assert flat[0]["customer.name"] == "Cust 0"
    assert "customer" not in flat[0]
    assert unflatten(flat) == NESTED


def test_flatten_makes_rows_tabular_and_cheaper():
    plain, rep_plain = EncodeStage(format="toon").run(NESTED, ctx())
    flat, rep_flat = EncodeStage(format="toon", flatten=True).run(NESTED, ctx())
    assert flat.splitlines()[0].startswith("[20]{order_id,customer.name,customer.city,total}:")
    assert rep_flat.tokens_after < rep_plain.tokens_after
    assert decode(flat, "toon", flattened=True) == NESTED


def test_auto_picks_the_cheapest_and_reports_candidates():
    text, rep = EncodeStage(format="auto").run(NESTED, ctx())
    cands = rep.meta["candidates"]
    assert set(cands) >= {"toon", "json"}
    assert rep.tokens_after == min(cands.values())
    assert rep.meta["format"] in cands
    # flat rows: csv is a candidate too and toon/csv should beat json
    text, rep = EncodeStage(format="auto").run([{"a": i, "b": "x"} for i in range(30)], ctx())
    assert "csv" in rep.meta["candidates"]
    assert rep.meta["format"] in ("toon", "csv")
