from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class InteractionRecord:
    timestamp: float
    app: str
    context_hash: str
    aria_message: str
    user_response: str
    action_taken: str
    outcome: str


class SQLiteMemoryStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                app TEXT,
                context_hash TEXT,
                aria_message TEXT,
                user_response TEXT,
                action_taken TEXT,
                outcome TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT UNIQUE,
                sentiment TEXT,
                frequency INTEGER,
                last_seen REAL,
                confidence REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_goals (
                date TEXT PRIMARY KEY,
                goal_text TEXT,
                progress_notes TEXT,
                completed INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_summaries (
                date TEXT PRIMARY KEY,
                interactions INTEGER,
                fixes_applied INTEGER,
                summary TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                role TEXT,
                content TEXT
            )
            """
        )
        self._conn.commit()

    def add_interaction(
        self,
        *,
        app: str,
        context_hash: str,
        aria_message: str,
        user_response: str,
        action_taken: str,
        outcome: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO interactions (timestamp, app, context_hash, aria_message, user_response, action_taken, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (time.time(), app, context_hash, aria_message, user_response, action_taken, outcome),
        )
        self._conn.commit()

    def recent_interactions(self, limit: int = 5) -> list[str]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT app, aria_message, user_response, outcome FROM interactions ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        lines = []
        for app, message, response, outcome in rows[::-1]:
            lines.append(f"{app}: {message} ({response or 'unknown'} / {outcome or 'unknown'})")
        return lines

    def interaction_count_since(self, since_ts: float) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM interactions WHERE timestamp >= ?",
            (since_ts,),
        )
        row = cur.fetchone()
        if not row:
            return 0
        return int(row[0] or 0)

    def latest_interaction(self) -> InteractionRecord | None:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT timestamp, app, context_hash, aria_message, user_response, action_taken, outcome
            FROM interactions
            ORDER BY id DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        return InteractionRecord(
            timestamp=float(row[0] or 0.0),
            app=str(row[1] or ""),
            context_hash=str(row[2] or ""),
            aria_message=str(row[3] or ""),
            user_response=str(row[4] or ""),
            action_taken=str(row[5] or ""),
            outcome=str(row[6] or ""),
        )

    def last_rejection(self, app: str) -> str:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT outcome FROM interactions
            WHERE app = ? AND outcome = 'rejected'
            ORDER BY id DESC LIMIT 1
            """,
            (app,),
        )
        row = cur.fetchone()
        if not row:
            return "none"
        return str(row[0] or "rejected")

    def update_preference(self, pattern: str, sentiment: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT frequency FROM preferences WHERE pattern = ?",
            (pattern,),
        )
        row = cur.fetchone()
        if row:
            frequency = int(row[0]) + 1
            confidence = min(1.0, 0.3 + (frequency * 0.1))
            cur.execute(
                """
                UPDATE preferences
                SET sentiment = ?, frequency = ?, last_seen = ?, confidence = ?
                WHERE pattern = ?
                """,
                (sentiment, frequency, time.time(), confidence, pattern),
            )
        else:
            cur.execute(
                """
                INSERT INTO preferences (pattern, sentiment, frequency, last_seen, confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pattern, sentiment, 1, time.time(), 0.35),
            )
        self._conn.commit()

    def top_preferences(self, app: str, limit: int = 3) -> list[str]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT pattern, sentiment, frequency, confidence
            FROM preferences
            WHERE pattern LIKE ?
            ORDER BY confidence DESC, frequency DESC
            LIMIT ?
            """,
            (f"%{app}%", limit),
        )
        rows = cur.fetchall()
        return [f"{pattern} ({sentiment}, {confidence:.2f})" for pattern, sentiment, _, confidence in rows]

    def set_today_goal(self, date_key: str, goal_text: str) -> None:
        self._conn.execute(
            """
            INSERT INTO session_goals (date, goal_text, progress_notes, completed)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET goal_text = excluded.goal_text
            """,
            (date_key, goal_text, "", 0),
        )
        self._conn.commit()

    def get_meta(self, key: str) -> str:
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM session_meta WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return ""
        return str(row[0] or "").strip()

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO session_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def save_session_summary(
        self,
        *,
        date_key: str,
        interactions: int,
        fixes_applied: int,
        summary: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO session_summaries (date, interactions, fixes_applied, summary)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                interactions = excluded.interactions,
                fixes_applied = excluded.fixes_applied,
                summary = excluded.summary
            """,
            (date_key, interactions, fixes_applied, summary),
        )
        self._conn.commit()

    def get_session_summary(self, date_key: str) -> tuple[int, int, str]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT interactions, fixes_applied, summary
            FROM session_summaries WHERE date = ?
            """,
            (date_key,),
        )
        row = cur.fetchone()
        if not row:
            return 0, 0, ""
        return int(row[0] or 0), int(row[1] or 0), str(row[2] or "")

    def count_interactions_between(self, start_ts: float, end_ts: float) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM interactions WHERE timestamp >= ? AND timestamp <= ?",
            (start_ts, end_ts),
        )
        row = cur.fetchone()
        return int(row[0] or 0)

    def count_fixes_between(self, start_ts: float, end_ts: float) -> int:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM interactions
            WHERE timestamp >= ? AND timestamp <= ? AND outcome = 'executed'
            """,
            (start_ts, end_ts),
        )
        row = cur.fetchone()
        return int(row[0] or 0)

    def get_goal(self, date_key: str) -> str:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT goal_text FROM session_goals WHERE date = ?",
            (date_key,),
        )
        row = cur.fetchone()
        if not row:
            return ""
        return str(row[0] or "").strip()

    def add_telegram_message(self, *, role: str, content: str) -> None:
        self._conn.execute(
            """
            INSERT INTO telegram_history (timestamp, role, content)
            VALUES (?, ?, ?)
            """,
            (time.time(), role, content),
        )
        self._conn.execute(
            """
            DELETE FROM telegram_history
            WHERE id NOT IN (
                SELECT id FROM telegram_history ORDER BY id DESC LIMIT 20
            )
            """
        )
        self._conn.commit()

    def recent_telegram_messages(self, limit: int = 5) -> list[tuple[str, str]]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT role, content FROM telegram_history
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [(str(role or "user"), str(content or "")) for role, content in rows[::-1]]

    def clear_telegram_history(self) -> None:
        self._conn.execute("DELETE FROM telegram_history")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def hash_context(text: str) -> str:
    return str(abs(hash(text)) % (10**10))
