from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class SQLiteStore:
    def __init__(self, path: str) -> None:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
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
            CREATE TABLE IF NOT EXISTS screen_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                task_text TEXT,
                context_json TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                task_text TEXT,
                plan_json TEXT,
                status TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_goals (
                date TEXT PRIMARY KEY,
                goal_text TEXT
            )
            """
        )
        self._conn.commit()

    def save_screen_snapshot(self, *, task_text: str, context: dict) -> None:
        self._conn.execute(
            "INSERT INTO screen_snapshots (timestamp, task_text, context_json) VALUES (?, ?, ?)",
            (time.time(), task_text, json.dumps(context, ensure_ascii=True)),
        )
        self._conn.commit()

    def save_task_record(self, *, task_text: str, plan: dict, status: str) -> None:
        self._conn.execute(
            "INSERT INTO task_history (timestamp, task_text, plan_json, status) VALUES (?, ?, ?, ?)",
            (time.time(), task_text, json.dumps(plan, ensure_ascii=True), status),
        )
        self._conn.commit()

    def recent_task_context(self, *, limit: int = 5) -> list[dict]:
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT th.task_text, ss.context_json
            FROM task_history th
            LEFT JOIN screen_snapshots ss ON ss.task_text = th.task_text
            ORDER BY th.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        result: list[dict] = []
        for task_text, context_json in rows:
            context = json.loads(context_json) if context_json else {}
            summary = {
                "last_task": task_text,
                "last_screen_summary": context.get("current_content", ""),
            }
            result.append(summary)
        return result

    def set_goal(self, *, date_key: str, goal_text: str) -> None:
        self._conn.execute(
            """
            INSERT INTO session_goals (date, goal_text)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET goal_text = excluded.goal_text
            """,
            (date_key, goal_text),
        )
        self._conn.commit()

    def get_goal(self, *, date_key: str) -> str:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT goal_text FROM session_goals WHERE date = ?",
            (date_key,),
        )
        row = cur.fetchone()
        if not row:
            return ""
        return str(row[0] or "").strip()

    def close(self) -> None:
        self._conn.close()
