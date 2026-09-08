import json

from typer.testing import CliRunner

from distillr.cli import app

runner = CliRunner()


def write_rows(tmp_path):
    rows = [{"id": i, "name": f"Item {i}", "city": "Berlin" if i % 2 else "Pune", "empty": None} for i in range(30)]
    p = tmp_path / "rows.json"
    p.write_text(json.dumps(rows, indent=2))
    return p


def test_analyze_json_report(tmp_path, monkeypatch):
    monkeypatch.setenv("DISTILLR_LEDGER", str(tmp_path / "l.db"))
    p = write_rows(tmp_path)
    res = runner.invoke(app, ["analyze", str(p), "--query", "Berlin", "--top-k", "5", "--json", "--no-ledger"])
    assert res.exit_code == 0, res.output
    rep = json.loads(res.stdout)
    assert rep["payload_kind"] == "tabular"
    assert rep["tokens_after"] < rep["tokens_before"]
    assert [s["name"] for s in rep["stages"]] == ["retrieve", "encode", "audit"]


def test_analyze_table_and_out(tmp_path):
    p = write_rows(tmp_path)
    out = tmp_path / "out.toon"
    res = runner.invoke(app, ["analyze", str(p), "--out", str(out), "--no-ledger", "--encode", "toon"])
    assert res.exit_code == 0, res.output
    assert "total" in res.stdout and out.exists()
    assert out.read_text().startswith("[30]{id,name,city}:")


def test_encode_and_decode_roundtrip(tmp_path):
    p = write_rows(tmp_path)
    res = runner.invoke(app, ["encode", str(p), "--format", "toon"])
    assert res.exit_code == 0
    t = tmp_path / "x.toon"
    t.write_text(res.stdout)
    back = runner.invoke(app, ["decode", str(t)])
    assert back.exit_code == 0
    assert json.loads(back.stdout) == json.loads(p.read_text())


def test_ledger_command(tmp_path):
    p = write_rows(tmp_path)
    db = tmp_path / "ledger.db"
    runner.invoke(app, ["analyze", str(p), "--tag", "t1"], env={"DISTILLR_LEDGER": str(db)})
    # Ledger default path is resolved at import; pass --path explicitly to be deterministic.
    res = runner.invoke(app, ["ledger", "--path", str(db)])
    assert res.exit_code == 0, res.output


def test_bad_format_exits_2(tmp_path):
    p = write_rows(tmp_path)
    assert runner.invoke(app, ["analyze", str(p), "--encode", "xml", "--no-ledger"]).exit_code == 2
