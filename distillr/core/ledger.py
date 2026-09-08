"""Token ledger: every compression run, before/after per stage, audit flags. SQLite by default
(zero-config, self-hosted); the hosted tier swaps the same schema onto Postgres."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .pipeline import CompressionResult


def default_path() -> Path:
    """Resolved at call time so DISTILLR_LEDGER can be set after import (tests, CLI wrappers)."""
    return Path(os.environ.get("DISTILLR_LEDGER", Path.home() / ".distillr" / "ledger.db"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  tag TEXT,
  payload_kind TEXT NOT NULL,
  encoding TEXT NOT NULL,
  tokenizer TEXT NOT NULL,
  query TEXT,
  tokens_before INTEGER NOT NULL,
  tokens_after INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  stages TEXT NOT NULL,      -- JSON list of stage reports
  removals INTEGER NOT NULL,
  manifest TEXT NOT NULL     -- JSON list of removals (previews truncated)
);
CREATE TABLE IF NOT EXISTS audits (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  flags INTEGER NOT NULL,
  high INTEGER NOT NULL,
  detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_time ON runs(created_at);
"""


@dataclass
class Summary:
    runs: int
    tokens_before: int
    tokens_after: int
    audits: int
    flagged_runs: int

    @property
    def saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def savings_pct(self) -> float:
        return 0.0 if self.tokens_before == 0 else 100.0 * self.saved / self.tokens_before


class Ledger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(SCHEMA)

    def record(self, r: CompressionResult, tag: str | None = None) -> None:
        manifest = [dict(m.to_dict(), preview=m.preview[:80]) for m in r.manifest]
        self.conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                r.id,
                r.created_at,
                tag,
                r.payload_kind,
                r.encoding,
                r.tokenizer,
                r.query,
                r.tokens_before,
                r.tokens_after,
                r.duration_ms,
                json.dumps([s.to_dict() for s in r.stages]),
                len(r.manifest),
                json.dumps(manifest),
            ),
        )
        self.conn.commit()

    def record_audit(self, run_id: str, flags: list) -> None:
        self.conn.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?)",
            (run_id, time.time(), len(flags), sum(1 for f in flags if f.risk == "high"), json.dumps([f.to_dict() for f in flags])),
        )
        self.conn.commit()

    def summary(self, days: float | None = None) -> Summary:
        since = time.time() - days * 86400 if days else 0
        row = self.conn.execute(
            "SELECT count(*), coalesce(sum(tokens_before),0), coalesce(sum(tokens_after),0) FROM runs WHERE created_at >= ?", (since,)
        ).fetchone()
        a = self.conn.execute(
            "SELECT count(*), count(DISTINCT CASE WHEN flags > 0 THEN run_id END) FROM audits WHERE created_at >= ?", (since,)
        ).fetchone()
        return Summary(row[0], row[1], row[2], a[0], a[1])

    def by_stage(self, days: float | None = None) -> dict[str, dict[str, int]]:
        since = time.time() - days * 86400 if days else 0
        agg: dict[str, dict[str, int]] = {}
        for (stages,) in self.conn.execute("SELECT stages FROM runs WHERE created_at >= ?", (since,)):
            for s in json.loads(stages):
                a = agg.setdefault(s["name"], {"tokens_before": 0, "tokens_after": 0, "runs": 0})
                a["tokens_before"] += s["tokens_before"]
                a["tokens_after"] += s["tokens_after"]
                a["runs"] += 1
        return agg

    def by_kind(self, days: float | None = None) -> list[tuple[str, int, int, int]]:
        since = time.time() - days * 86400 if days else 0
        return self.conn.execute(
            "SELECT payload_kind, count(*), sum(tokens_before), sum(tokens_after) FROM runs "
            "WHERE created_at >= ? GROUP BY payload_kind ORDER BY 3 DESC",
            (since,),
        ).fetchall()

    def recent(self, n: int = 20) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        rows = self.conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (n,)).fetchall()
        self.conn.row_factory = None
        return rows

    def export(self) -> list[dict]:
        self.conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in self.conn.execute("SELECT * FROM runs ORDER BY created_at")]
        self.conn.row_factory = None
        for r in rows:
            r["stages"] = json.loads(r["stages"])
            r["manifest"] = json.loads(r["manifest"])
        return rows

    def close(self) -> None:
        self.conn.close()
