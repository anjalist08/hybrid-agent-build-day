"""SQLite knowledge base: frames -> impressions -> entities, plus a routing log."""

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    device TEXT NOT NULL,
    dhash TEXT NOT NULL,
    app TEXT,
    screen_kind TEXT,
    sensitive INTEGER NOT NULL DEFAULT 0,
    extractor TEXT,
    observation TEXT
);

CREATE TABLE IF NOT EXISTS impressions (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    app TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    url TEXT,
    summary TEXT,
    topics TEXT NOT NULL DEFAULT '[]',
    ts_start REAL NOT NULL,
    ts_end REAL NOT NULL,
    dwell_s REAL NOT NULL,
    frame_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_impressions_key ON impressions(key, ts_end);
CREATE INDEX IF NOT EXISTS idx_impressions_ts ON impressions(ts_end);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,          -- topic | person | app
    name TEXT NOT NULL,
    UNIQUE(type, name)
);

CREATE TABLE IF NOT EXISTS impression_entities (
    impression_id INTEGER NOT NULL REFERENCES impressions(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (impression_id, entity_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS impressions_fts USING fts5(
    title, author, summary, topics, app
);

CREATE TABLE IF NOT EXISTS route_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    op TEXT NOT NULL,            -- extract | query
    location TEXT NOT NULL,      -- device | local | cloud
    model TEXT,
    ms INTEGER,
    ok INTEGER NOT NULL,
    detail TEXT
);
"""


class DB:
    """Thin wrapper around one SQLite connection shared across threads behind a lock."""

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def log_route(self, op: str, location: str, model: str | None, ms: int, ok: bool, detail: str = "") -> None:
        self.execute(
            "INSERT INTO route_log(ts, op, location, model, ms, ok, detail) VALUES (?,?,?,?,?,?,?)",
            (time.time(), op, location, model, ms, int(ok), detail[:500]),
        )

    def wipe(self) -> None:
        with self.lock:
            for table in ("impression_entities", "entities", "impressions", "impressions_fts", "frames", "route_log"):
                self.conn.execute(f"DELETE FROM {table}")
            self.conn.commit()


def row_topics(row: dict) -> list[str]:
    try:
        return json.loads(row.get("topics") or "[]")
    except json.JSONDecodeError:
        return []
