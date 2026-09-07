from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    question_text: str
    full_answer: str
    timestamp_ms: int
    duration_ms: int


class SessionStore:
    def __init__(self, path: str, enabled: bool):
        self._path = path
        self._enabled = enabled
        self._conn: sqlite3.Connection | None = None
        self._session_id: int | None = None
        if not enabled:
            return
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(file_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, started_at_ms INTEGER NOT NULL)"
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
              id INTEGER PRIMARY KEY,
              session_id INTEGER NOT NULL,
              question_text TEXT NOT NULL,
              full_answer TEXT NOT NULL,
              timestamp_ms INTEGER NOT NULL,
              duration_ms INTEGER NOT NULL,
              FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """
        )
        self._conn.commit()

    def start_session(self) -> int:
        if not self._enabled or self._conn is None:
            return 0
        import time

        cur = self._conn.execute(
            "INSERT INTO sessions (started_at_ms) VALUES (?)",
            (int(time.time() * 1000),),
        )
        self._conn.commit()
        self._session_id = int(cur.lastrowid)
        return self._session_id

    def append(self, question_text: str, full_answer: str, timestamp_ms: int, duration_ms: int) -> None:
        if not self._enabled or self._conn is None or self._session_id is None:
            return
        self._conn.execute(
            """
            INSERT INTO entries (session_id, question_text, full_answer, timestamp_ms, duration_ms)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self._session_id, question_text, full_answer, timestamp_ms, duration_ms),
        )
        self._conn.commit()

    def list_sessions(self) -> list[dict]:
        if not self._enabled or self._conn is None:
            return []
        rows = self._conn.execute(
            "SELECT id, started_at_ms FROM sessions ORDER BY id DESC"
        ).fetchall()
        sessions = []
        for session_id, started_at_ms in rows:
            sessions.append(
                {
                    "id": session_id,
                    "started_at_ms": started_at_ms,
                    "entries": [
                        {
                            "id": entry.id,
                            "question_text": entry.question_text,
                            "full_answer": entry.full_answer,
                            "timestamp_ms": entry.timestamp_ms,
                            "duration_ms": entry.duration_ms,
                        }
                        for entry in self.list_entries(session_id)
                    ],
                }
            )
        return sessions

    def list_entries(self, session_id: int) -> list[HistoryEntry]:
        if not self._enabled or self._conn is None:
            return []
        rows = self._conn.execute(
            """
            SELECT id, question_text, full_answer, timestamp_ms, duration_ms
            FROM entries WHERE session_id = ? ORDER BY id
            """,
            (session_id,),
        ).fetchall()
        return [
            HistoryEntry(
                id=row[0],
                question_text=row[1],
                full_answer=row[2],
                timestamp_ms=row[3],
                duration_ms=row[4],
            )
            for row in rows
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
