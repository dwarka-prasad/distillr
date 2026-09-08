"""distillr CLI: analyze a payload, encode it, inspect the ledger, run the benchmarks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .core import AuditStage, EncodeStage, Ledger, Pipeline, RetrieveStage, load
from .core.stages.encode import FORMATS

app = typer.Typer(help="Distillr: compress LLM inputs and account for every token saved.", no_args_is_help=True, add_completion=False)
console = Console()
err = Console(stderr=True)


def _version(v: bool):
    if v:
        console.print(f"distillr {__version__}")
        raise typer.Exit()


@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show version")):
    pass


@app.command()
def analyze(
    file: Path = typer.Argument(..., exists=True, readable=True, help="JSON, JSONL, CSV or text payload"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Rank items by relevance to this query"),
    top_k: Optional[int] = typer.Option(None, "--top-k", "-k", help="Keep at most K items (most relevant with --query)"),
    encode: str = typer.Option("auto", "--encode", "-e", help=f"Output format: {', '.join(FORMATS)} (auto = fewest tokens)"),
    flatten: bool = typer.Option(False, "--flatten", help="Flatten nested objects into dotted columns before encoding"),
    keep_fields: Optional[str] = typer.Option(None, "--fields", help="Comma-separated field globs to keep, e.g. id,name,*_at"),
    drop_fields: Optional[str] = typer.Option(None, "--drop", help="Comma-separated field globs to drop"),
    keep_last: Optional[int] = typer.Option(None, "--keep-last", help="Chat: always keep the last N messages"),
    max_chars: Optional[int] = typer.Option(None, "--max-chars", help="Truncate strings longer than this"),
    no_drop_empty: bool = typer.Option(False, "--keep-empty", help="Do not remove null/empty fields"),
    tokenizer: Optional[str] = typer.Option(None, "--tokenizer", "-t", help="tiktoken encoding (o200k_base, cl100k_base)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Pick the tokenizer for a model id, e.g. gpt-4o, claude-sonnet-5"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write the compressed text here"),
    show: bool = typer.Option(False, "--show", help="Print the compressed text"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable report"),
    no_ledger: bool = typer.Option(False, "--no-ledger", help="Do not record this run in the ledger"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Label for the ledger (endpoint, feature, ...)"),
):
    """Compress a payload and print before/after token counts per stage."""
    if encode not in FORMATS:
        err.print(f"[red]unknown format {encode!r}; choose from {', '.join(FORMATS)}")
        raise typer.Exit(2)
    payload = load(file)
    stages = [
        RetrieveStage(
            query=query,
            top_k=top_k,
            keep_fields=_csv(keep_fields),
            drop_fields=_csv(drop_fields),
            drop_empty=not no_drop_empty,
            max_string_chars=max_chars,
            keep_last_messages=keep_last,
        ),
        EncodeStage(format=encode, flatten=flatten),
        AuditStage(),
    ]
    result = Pipeline(stages, tokenizer=tokenizer, model=model).run(payload, query=query)
    if not no_ledger:
        Ledger().record(result, tag=tag or str(file.name))
    if out:
        out.write_text(result.text, encoding="utf-8")

    if as_json:
        console.print_json(json.dumps(result.to_dict(include_text=show)))
        return

    title = f"[bold]{file.name}[/bold]  kind=[cyan]{payload.kind}[/cyan]  tokenizer={result.tokenizer}"
    t = Table(title=title, show_lines=False, expand=False)
    t.add_column("Stage", style="bold")
    t.add_column("Tokens in", justify="right")
    t.add_column("Tokens out", justify="right")
    t.add_column("Saved", justify="right")
    t.add_column("%", justify="right")
    t.add_column("Notes", style="dim")
    for s in result.stages:
        notes = []
        if s.name == "retrieve":
            if s.meta.get("kept") is not None:
                notes.append(f"kept {s.meta['kept']}/{s.meta['input']} items")
            notes.append(f"{len(s.removals)} removals")
        elif s.name == "encode":
            notes.append(s.meta.get("format", ""))
            if s.meta.get("candidates"):
                notes.append("auto: " + " ".join(f"{k}={v:,}" for k, v in s.meta["candidates"].items()))
            if s.meta.get("flattened"):
                notes.append("flattened")
            notes.append("lossless")
        elif s.name == "audit":
            br = s.meta.get("by_risk", {})
            notes.append(f"risk high={br.get('high', 0)} med={br.get('medium', 0)} low={br.get('low', 0)}")
        color = "green" if s.saved > 0 else "dim"
        t.add_row(
            s.name,
            f"{s.tokens_before:,}",
            f"{s.tokens_after:,}",
            f"[{color}]{s.saved:,}[/{color}]",
            f"[{color}]{s.savings_pct:.1f}%[/{color}]",
            " · ".join(notes),
        )
    t.add_row(
        "[bold]total[/bold]",
        f"[bold]{result.tokens_before:,}",
        f"[bold]{result.tokens_after:,}",
        f"[bold green]{result.saved:,}",
        f"[bold green]{result.savings_pct:.1f}%",
        f"{result.duration_ms} ms",
        end_section=True,
    )
    console.print(t)
    if "(approx)" in result.tokenizer:
        err.print("[yellow]tokenizer files unavailable, counts are approximate (chars/4). Run once online to download tiktoken encodings.")
    if show:
        console.print(Panel(result.text, title=f"compressed ({result.encoding})", border_style="dim"))
    if out:
        console.print(f"[dim]wrote {out}")


@app.command()
def encode(
    file: Path = typer.Argument(..., exists=True),
    format: str = typer.Option("auto", "--format", "-f", help=f"{', '.join(FORMATS)}"),
    flatten: bool = typer.Option(False, "--flatten"),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
):
    """Re-encode a payload (no trimming) and print it."""
    payload = load(file)
    text, rep = EncodeStage(format=format, flatten=flatten).run(payload.data, _ctx(payload))
    if out:
        out.write_text(text, encoding="utf-8")
        cands = f"  {rep.meta['candidates']}" if rep.meta.get("candidates") else ""
        console.print(f"[dim]wrote {out}  {rep.meta.get('format')}: {rep.tokens_before:,} -> {rep.tokens_after:,} tokens{cands}")
    else:
        # stdout carries only the encoded text so it can be piped or fed to `distillr decode`
        sys.stdout.write(text + "\n")


@app.command()
def decode(
    file: Path = typer.Argument(..., exists=True),
    format: str = typer.Option("toon", "--format", "-f"),
    flattened: bool = typer.Option(False, "--flattened", help="Input was produced with --flatten"),
):
    """Decode TOON/CSV back to JSON (proves the encode stage is lossless)."""
    from .core.stages.encode import decode as _decode

    sys.stdout.write(json.dumps(_decode(file.read_text(encoding="utf-8"), format, flattened), indent=2, ensure_ascii=False) + "\n")


@app.command()
def ledger(
    days: Optional[float] = typer.Option(None, "--days", "-d", help="Only the last N days"),
    recent: int = typer.Option(10, "--recent", "-n", help="Show the N most recent runs"),
    export: Optional[Path] = typer.Option(None, "--export", help="Write all runs as JSON"),
    path: Optional[Path] = typer.Option(None, "--path", help="Ledger file (default ~/.distillr/ledger.db)"),
):
    """Token savings recorded so far: totals, per stage, per payload kind, recent runs."""
    lg = Ledger(path)
    if export:
        export.write_text(json.dumps(lg.export(), indent=2))
        console.print(f"[dim]wrote {export}")
        return
    s = lg.summary(days)
    console.print(
        Panel(
            f"[bold]{s.runs:,}[/bold] runs   [bold]{s.tokens_before:,}[/bold] tokens in   [bold]{s.tokens_after:,}[/bold] out   "
            f"[bold green]{s.saved:,} saved ({s.savings_pct:.1f}%)[/bold green]   audits: {s.audits} ({s.flagged_runs} flagged)",
            title=f"Distillr ledger · {lg.path}",
            border_style="green",
        )
    )
    if s.runs == 0:
        return
    t = Table(title="By stage")
    t.add_column("Stage")
    t.add_column("Runs", justify="right")
    t.add_column("Tokens in", justify="right")
    t.add_column("Tokens out", justify="right")
    t.add_column("Saved %", justify="right")
    for name, a in lg.by_stage(days).items():
        pct = 0 if a["tokens_before"] == 0 else 100 * (a["tokens_before"] - a["tokens_after"]) / a["tokens_before"]
        t.add_row(name, str(a["runs"]), f"{a['tokens_before']:,}", f"{a['tokens_after']:,}", f"{pct:.1f}%")
    console.print(t)
    k = Table(title="By payload kind")
    k.add_column("Kind")
    k.add_column("Runs", justify="right")
    k.add_column("Tokens in", justify="right")
    k.add_column("Saved %", justify="right")
    for kind, n, b, a in lg.by_kind(days):
        k.add_row(kind, str(n), f"{b:,}", f"{0 if not b else 100 * (b - a) / b:.1f}%")
    console.print(k)
    r = Table(title=f"Recent {recent}")
    r.add_column("When")
    r.add_column("Tag")
    r.add_column("Kind")
    r.add_column("Enc")
    r.add_column("In", justify="right")
    r.add_column("Out", justify="right")
    r.add_column("Saved %", justify="right")
    r.add_column("Removals", justify="right")
    import datetime as dt

    for row in lg.recent(recent):
        when = dt.datetime.fromtimestamp(row["created_at"]).strftime("%m-%d %H:%M")
        pct = 0 if not row["tokens_before"] else 100 * (row["tokens_before"] - row["tokens_after"]) / row["tokens_before"]
        r.add_row(
            when,
            row["tag"] or "",
            row["payload_kind"],
            row["encoding"],
            f"{row['tokens_before']:,}",
            f"{row['tokens_after']:,}",
            f"{pct:.1f}%",
            str(row["removals"]),
        )
    console.print(r)


@app.command()
def bench(write: bool = typer.Option(True, "--write/--no-write", help="Write benchmarks/RESULTS.md")):
    """Run the Phase 0 benchmark suite (token savings + needle recall on 5 payload types)."""
    root = Path(__file__).resolve().parent.parent / "benchmarks"
    if not (root / "run.py").exists():
        err.print("[red]benchmarks/ not found next to the package (run from a source checkout)")
        raise typer.Exit(2)
    sys.path.insert(0, str(root))
    import run as bench_run  # type: ignore

    bench_run.main(write=write)


def _csv(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _ctx(payload):
    from .core.stages.base import Context
    from .core.tokenizers import TokenCounter

    return Context(TokenCounter(), payload.kind)


if __name__ == "__main__":  # pragma: no cover
    app()
