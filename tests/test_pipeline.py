import json

import distillr
from distillr.core import AuditStage, EncodeStage, Ledger, Pipeline, RetrieveStage, detect_kind, wrap
from distillr.core.stages.base import Context
from distillr.core.stages.retrieve import BM25, tokenize
from distillr.core.tokenizers import TokenCounter

ROWS = [
    {
        "id": i,
        "customer": f"Cust {i}",
        "city": "Berlin" if i % 7 == 0 else "Pune",
        "status": "shipped" if i % 3 else "cancelled",
        "notes": "",
        "ref": None,
        "amount": i * 10.0,
    }
    for i in range(60)
]
ROWS[21]["customer"] = "Ada Lovelace"
CHAT = {
    "messages": [{"role": "system", "content": "Be brief."}]
    + [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i} about topic {i % 5}"} for i in range(30)]
}
CHAT["messages"][8]["content"] = "My order ORD-999 needs a refund of $640"


def ctx(kind="tabular", query=None):
    return Context(TokenCounter(), kind, query)


def test_detect_kind():
    assert detect_kind(ROWS) == "tabular"
    assert detect_kind(CHAT) == "chat"
    assert detect_kind([{"text": "a"}, {"text": "b"}]) == "chunks"
    assert detect_kind({"a": 1}) == "object"
    assert detect_kind("hi") == "text"


def test_retrieve_keeps_sparse_columns_so_rows_stay_uniform():
    rows = [{"id": 1, "note": None}, {"id": 2, "note": "keep me"}, {"id": 3, "note": None}]
    out, rep = RetrieveStage().run(rows, ctx())
    assert all("note" in r for r in out), "a column with any value must survive in every row"
    assert rep.removals == []


def test_retrieve_drops_empty_fields_and_records_removals():
    out, rep = RetrieveStage().run(ROWS, ctx())
    assert all("notes" not in r and "ref" not in r for r in out)
    assert rep.tokens_after < rep.tokens_before
    kinds = {r.kind for r in rep.removals}
    assert kinds == {"field"}
    assert all(r.reason in ("empty value", "empty in every row") for r in rep.removals)


def test_retrieve_ranks_by_query_and_keeps_needle():
    out, rep = RetrieveStage(query="Ada Lovelace Berlin", top_k=5).run(ROWS, ctx())
    assert len(out) == 5
    assert any(r["customer"] == "Ada Lovelace" for r in out)
    dropped = [r for r in rep.removals if r.kind == "item"]
    assert len(dropped) == 55
    assert all("low relevance" in r.reason for r in dropped)


def test_retrieve_field_allowlist_and_denylist():
    out, _ = RetrieveStage(keep_fields=["id", "cit*"]).run(ROWS[:3], ctx())
    assert set(out[0]) == {"id", "city"}
    out, _ = RetrieveStage(drop_fields=["amount"]).run(ROWS[:3], ctx())
    assert "amount" not in out[0]


def test_retrieve_chat_keeps_system_and_recent_and_relevant():
    out, rep = RetrieveStage(query="refund order", top_k=6, keep_last_messages=4).run(CHAT, ctx("chat"))
    msgs = out["messages"]
    assert msgs[0]["role"] == "system"
    assert any("ORD-999" in m["content"] for m in msgs)
    assert [m["content"] for m in msgs[-4:]] == [m["content"] for m in CHAT["messages"][-4:]]
    assert len(msgs) <= 6 + 1


def test_truncation_records_removed_tail():
    data = [{"id": 1, "body": "x" * 500}]
    out, rep = RetrieveStage(max_string_chars=100).run(data, ctx())
    assert len(out[0]["body"]) == 101
    assert rep.removals[0].kind == "truncation"


def test_bm25_prefers_matching_docs():
    docs = [tokenize(t) for t in ["apple banana", "banana cherry", "refund order monitor"]]
    bm = BM25(docs)
    q = tokenize("refund monitor")
    scores = [bm.score(q, i) for i in range(3)]
    assert scores[2] > scores[0] and scores[2] > scores[1]


def test_pipeline_totals_and_encode_is_lossless():
    r = Pipeline([RetrieveStage(), EncodeStage(format="toon"), AuditStage()]).run(wrap(ROWS))
    assert r.tokens_after < r.tokens_before
    assert r.stages[0].tokens_before == r.tokens_before
    assert r.encoding == "toon"
    from distillr.core.toon import decode

    cleaned = [{k: v for k, v in row.items() if v not in (None, "")} for row in ROWS]
    assert decode(r.text) == cleaned


def test_compress_sdk_entry_point(tmp_path, monkeypatch):
    monkeypatch.setenv("DISTILLR_LEDGER", str(tmp_path / "ledger.db"))
    import importlib

    import distillr.core.ledger as lg

    importlib.reload(lg)
    r = distillr.compress(ROWS, query="Ada Lovelace", top_k=3, ledger=False)
    assert r.savings_pct > 50
    assert "Ada Lovelace" in r.text


def test_audit_flags_answer_that_uses_removed_content():
    r = Pipeline([RetrieveStage(query="Berlin", top_k=3), EncodeStage()]).run(wrap(ROWS), query="Berlin")
    # Cust 5 was removed (not in Berlin, low relevance). If the model mentions it, flag it.
    flags = r.check_answer("The customer Cust 5 paid 50.0 for the order.")
    assert flags, "expected a flag for referencing removed row"
    assert flags[0].stage == "retrieve"
    assert r.check_answer("Berlin orders are shipped.") == []


def test_encode_formats():
    for fmt in ("toon", "json", "csv"):
        text, rep = EncodeStage(format=fmt).run(ROWS[:5], ctx())
        assert rep.meta["format"] == fmt and rep.tokens_after > 0
    text, rep = EncodeStage(format="csv").run({"a": {"b": 1}}, ctx("object"))
    assert rep.meta["format"] == "toon"  # csv falls back for non-tabular
    text, _ = EncodeStage(format="json").run(ROWS[:2], ctx())
    assert json.loads(text) == ROWS[:2]


def test_ledger_records_and_summarizes():
    lg = Ledger(":memory:")
    r = Pipeline([RetrieveStage(), EncodeStage()]).run(wrap(ROWS))
    lg.record(r, tag="test")
    lg.record_audit(r.id, r.check_answer("nothing removed here"))
    s = lg.summary()
    assert s.runs == 1 and s.tokens_before == r.tokens_before and s.saved > 0
    assert lg.by_stage()["encode"]["runs"] == 1
    assert lg.by_kind()[0][0] == "tabular"
    assert lg.recent(1)[0]["tag"] == "test"
    assert lg.export()[0]["stages"][0]["name"] == "retrieve"


def test_token_counter_exact_or_flagged():
    c = TokenCounter("o200k_base")
    n = c.count("hello world")
    assert n > 0
    assert c.exact or "(approx)" in c.label
