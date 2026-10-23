"""SQLite storage (built into Python, nothing to install).

Why SQLite and not DuckDB: the web app writes (live snapshots, paper bets) while it reads.  SQLite in WAL
mode allows that from many threads; DuckDB allows only one writing process and locks the file on Windows.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY, sport TEXT, competition TEXT, date TEXT, home TEXT, away TEXT,
    home_score REAL, away_score REAL, source TEXT, extra TEXT);
CREATE INDEX IF NOT EXISTS ix_results_sport ON results(sport, competition, date);
CREATE TABLE IF NOT EXISTS slips (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, stake REAL, legs TEXT, status TEXT,
    pnl REAL DEFAULT 0, settled_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS user_odds (
    event_id TEXT, key TEXT, odds REAL, updated_at TEXT, PRIMARY KEY (event_id, key));
CREATE TABLE IF NOT EXISTS predictions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event_id TEXT, key TEXT, prob REAL, odds_market REAL, model TEXT);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._mem_conn = None
        if self.path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", timeout=30, check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.executescript(SCHEMA)
            self._mem_conn.commit()
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with self.conn() as c:
                c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        if self.path == ":memory:" and self._mem_conn is not None:
            yield self._mem_conn
            self._mem_conn.commit()
            return
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            yield con
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------ key-value
    def kv_get(self, key: str, default: Any = None) -> Any:
        with self.conn() as c:
            row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def kv_set(self, key: str, value: Any) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                      (key, json.dumps(value, default=str), datetime.now(timezone.utc).isoformat()))

    # ------------------------------------------------------------------ soccer matches (wide table)
    def save_matches(self, df: pd.DataFrame) -> None:
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        with self.conn() as c:
            d.to_sql("matches", c, if_exists="replace", index=False)
            c.execute("CREATE INDEX IF NOT EXISTS ix_matches_league ON matches(league, date)")

    def load_matches(self, league: Optional[str] = None, since: Optional[str] = None) -> pd.DataFrame:
        with self.conn() as c:
            has = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'").fetchone()
            if not has:
                return pd.DataFrame()
            sql, args = "SELECT * FROM matches WHERE 1=1", []
            if league:
                sql += " AND league=?"
                args.append(league)
            if since:
                sql += " AND date>=?"
                args.append(since)
            df = pd.read_sql_query(sql, c, params=args)
        if len(df):
            df["date"] = pd.to_datetime(df["date"])
        return df

    def match_counts(self) -> Dict[str, int]:
        with self.conn() as c:
            has = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'").fetchone()
            if not has:
                return {}
            return {r["league"]: r["n"] for r in c.execute("SELECT league, COUNT(*) n FROM matches GROUP BY league")}

    # ------------------------------------------------------------------ generic results (other sports, live feed)
    def add_result(self, rid: str, sport: str, competition: str, date: str, home: str, away: str,
                   hs: float, as_: float, source: str = "", extra: Optional[dict] = None) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (rid, sport, competition, date, home, away, hs, as_, source, json.dumps(extra or {})))

    def load_results(self, sport: Optional[str] = None, competition: Optional[str] = None) -> pd.DataFrame:
        sql, args = "SELECT * FROM results WHERE 1=1", []
        if sport:
            sql += " AND sport=?"
            args.append(sport)
        if competition:
            sql += " AND competition=?"
            args.append(competition)
        with self.conn() as c:
            df = pd.read_sql_query(sql, c, params=args)
        if len(df):
            df["date"] = pd.to_datetime(df["date"])
        return df

    # ------------------------------------------------------------------ user odds (prices typed from a sportsbook)
    def set_user_odds(self, event_id: str, key: str, odds: Optional[float]) -> None:
        with self.conn() as c:
            if odds is None:
                c.execute("DELETE FROM user_odds WHERE event_id=? AND key=?", (event_id, key))
            else:
                c.execute("INSERT OR REPLACE INTO user_odds VALUES(?,?,?,?)",
                          (event_id, key, float(odds), datetime.now(timezone.utc).isoformat()))

    def get_user_odds(self, event_id: str) -> Dict[str, float]:
        with self.conn() as c:
            return {r["key"]: r["odds"] for r in c.execute("SELECT key, odds FROM user_odds WHERE event_id=?", (event_id,))}

    # ------------------------------------------------------------------ paper slips
    def add_slip(self, stake: float, legs: List[dict], note: str = "") -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO slips(created_at,stake,legs,status,note) VALUES(?,?,?,?,?)",
                            (datetime.now(timezone.utc).isoformat(), stake, json.dumps(legs), "open", note))
            return int(cur.lastrowid)

    def list_slips(self, status: Optional[str] = None) -> List[dict]:
        sql, args = "SELECT * FROM slips", []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY id DESC"
        with self.conn() as c:
            rows = c.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["legs"] = json.loads(d["legs"])
            out.append(d)
        return out

    def update_slip(self, slip_id: int, legs: List[dict], status: str, pnl: float) -> None:
        with self.conn() as c:
            c.execute("UPDATE slips SET legs=?, status=?, pnl=?, settled_at=? WHERE id=?",
                      (json.dumps(legs), status, pnl,
                       datetime.now(timezone.utc).isoformat() if status != "open" else None, slip_id))

    def delete_slip(self, slip_id: int) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM slips WHERE id=?", (slip_id,))
