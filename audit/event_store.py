"""Append-only SQLite event store (event sourcing).

Every audited mutation is one immutable row. ``seq`` is monotonic **per match**
and is derived from the stored max, so it survives process restarts (crash
recovery). :meth:`replay` folds the stored events back into a ``MatchState`` at
any point in time.

Audit granularity (see plan): discrete game-state mutations only — never the
~30 Hz movement stream. WAL mode keeps appends cheap and non-blocking.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id  TEXT NOT NULL,
  seq       INTEGER NOT NULL,      -- monotonic per match
  ts        REAL NOT NULL,
  type      TEXT NOT NULL,         -- damage | hp_change | hero_select | transition | round_result | join | leave
  actor     TEXT,                  -- p1 | p2 | system
  payload   TEXT NOT NULL          -- JSON
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_match_seq ON events(match_id, seq);
"""


class EventStore:
    def __init__(self, db_path: str = "audit.db") -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ write
    def append(self, match_id: str, type: str, actor: Optional[str], payload: dict) -> int:
        """Append one immutable event; returns the assigned per-match ``seq``."""
        seq = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE match_id = ?", (match_id,)
        ).fetchone()[0]
        self._conn.execute(
            "INSERT INTO events(match_id, seq, ts, type, actor, payload) VALUES (?, ?, ?, ?, ?, ?)",
            (match_id, seq, time.time(), type, actor, json.dumps(payload, separators=(",", ":"))),
        )
        self._conn.commit()
        return seq

    # ------------------------------------------------------------------- read
    def events_for(self, match_id: str, upto_seq: Optional[int] = None) -> list[dict]:
        if upto_seq is None:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE match_id = ? ORDER BY seq", (match_id,)
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE match_id = ? AND seq <= ? ORDER BY seq",
                (match_id, upto_seq),
            )
        return [self._row_to_event(r) for r in rows.fetchall()]

    def matches(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT match_id FROM events ORDER BY match_id")
        return [r[0] for r in rows.fetchall()]

    def replay(self, match_id: str, upto_seq: Optional[int] = None):
        """Reconstruct match state at ``upto_seq`` (or latest) from the log."""
        # Lazy import keeps the store importable on its own and avoids cycles.
        from coordinator.match_state import MatchState

        return MatchState.from_events(match_id, self.events_for(match_id, upto_seq))

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> dict:
        return {
            "id": r["id"],
            "match_id": r["match_id"],
            "seq": r["seq"],
            "ts": r["ts"],
            "type": r["type"],
            "actor": r["actor"],
            "payload": json.loads(r["payload"]),
        }
