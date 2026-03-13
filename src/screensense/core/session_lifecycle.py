from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from screensense.integrations.voice import VoiceOutput
from screensense.memory.sqlite_store import SQLiteMemoryStore


@dataclass(slots=True)
class GoalCaptureResult:
    accepted: bool
    response: str


class SessionLifecycle:
    def __init__(
        self,
        *,
        memory_db: SQLiteMemoryStore,
        voice: VoiceOutput,
        deadline_date: str,
        user_name: str,
        send_telegram: Callable[[str], None] | None = None,
        whisper_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._memory_db = memory_db
        self._voice = voice
        self._deadline_date = deadline_date.strip()
        self._user_name = user_name.strip() or "Operator"
        self._send_telegram = send_telegram
        self._whisper_callback = whisper_callback
        self._awaiting_goal = False
        self._awaiting_since = 0.0
        self._last_away = False
        self._away_start_ts = 0.0
        self._last_long_session_ts = 0.0
        self._session_start_ts = time.time()
        # Persist session start for external consumers (e.g. Telegram).
        try:
            self._memory_db.set_meta("session_start_ts", str(self._session_start_ts))
        except Exception:
            pass

    def on_startup(self) -> None:
        today_key = self._today_key()
        last_date = self._memory_db.get_meta("last_session_date")
        if last_date != today_key:
            self._memory_db.set_meta("last_session_date", today_key)
            self._morning_brief()

    def on_tick(self, *, away: bool) -> None:
        if away and not self._last_away:
            self._away_start_ts = time.time()
        if not away and self._last_away:
            self._on_return_from_away()
        self._last_away = away
        self._maybe_long_session_nudge()

    def on_shutdown(self) -> None:
        self._save_session_summary()
        session_minutes = int((time.time() - self._session_start_ts) // 60)
        if session_minutes >= 30:
            interactions = self._memory_db.interaction_count_since(self._session_start_ts)
            self._voice.speak_event(
                f"good session. {interactions} things handled.",
                context="Session",
                confidence=0.98,
            )

    def maybe_capture_goal(self, text: str) -> GoalCaptureResult | None:
        if not self._awaiting_goal:
            return None
        goal = text.strip()
        if not goal:
            return GoalCaptureResult(accepted=False, response="need a goal to proceed.")
        self._memory_db.set_today_goal(self._today_key(), goal)
        self._awaiting_goal = False
        self._awaiting_since = 0.0
        response = f"got it. {goal}."
        return GoalCaptureResult(accepted=True, response=response)

    def is_waiting_for_goal(self) -> bool:
        return self._awaiting_goal

    def _morning_brief(self) -> None:
        greeting = self._time_greeting()
        self._voice.speak_event(
            f"{greeting} {self._user_name}",
            context="Session",
            confidence=0.98,
        )
        days_left = self._days_to_deadline()
        if days_left is not None:
            self._voice.speak_event(f"{days_left} days to deadline.", context="Session")
        interactions, fixes = self._yesterday_stats()
        self._voice.speak_event(
            f"yesterday: {interactions} interactions, {fixes} fixes applied.",
            context="Session",
        )
        prompt = "what are we focusing on today?"
        self._voice.speak_event(prompt, context="Session")
        if self._send_telegram is not None:
            self._send_telegram(prompt)
        if self._whisper_callback is not None:
            self._whisper_callback(prompt)
        self._awaiting_goal = True
        self._awaiting_since = time.time()

    def _on_return_from_away(self) -> None:
        message = "welcome back."
        latest = self._memory_db.latest_interaction()
        if latest and latest.timestamp >= self._away_start_ts:
            message = f"welcome back. one thing while you were out — {latest.aria_message}"
        self._voice.speak_event(message, context="Session", confidence=0.96)

    def _maybe_long_session_nudge(self) -> None:
        now = time.time()
        session_minutes = int((now - self._session_start_ts) // 60)
        if session_minutes < 90:
            return
        if self._last_long_session_ts and (now - self._last_long_session_ts) < (90 * 60):
            return
        self._last_long_session_ts = now
        self._voice.speak_mode("earcon", mode="earcon", context="Session")
        if self._whisper_callback is not None:
            self._whisper_callback("been at it 90 min.")

    def _save_session_summary(self) -> None:
        start_ts = self._session_start_ts
        end_ts = time.time()
        interactions = self._memory_db.count_interactions_between(start_ts, end_ts)
        fixes = self._memory_db.count_fixes_between(start_ts, end_ts)
        summary = f"session: {interactions} interactions, {fixes} fixes."
        self._memory_db.save_session_summary(
            date_key=self._today_key(),
            interactions=interactions,
            fixes_applied=fixes,
            summary=summary,
        )

    def _yesterday_stats(self) -> tuple[int, int]:
        today = datetime.now().date()
        start = datetime.combine(today - timedelta(days=1), datetime.min.time())
        end = datetime.combine(today - timedelta(days=1), datetime.max.time())
        interactions = self._memory_db.count_interactions_between(
            start.timestamp(), end.timestamp()
        )
        fixes = self._memory_db.count_fixes_between(start.timestamp(), end.timestamp())
        return interactions, fixes

    def _time_greeting(self) -> str:
        hour = datetime.now().hour
        if 0 <= hour < 5:
            return "still at it?"
        if 5 <= hour < 12:
            return "good morning"
        if 12 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 23:
            return "evening"
        return "still at it?"

    def _days_to_deadline(self) -> int | None:
        if not self._deadline_date:
            return None
        try:
            deadline = datetime.fromisoformat(self._deadline_date).date()
        except ValueError:
            return None
        return (deadline - datetime.now().date()).days

    @staticmethod
    def _today_key() -> str:
        return time.strftime("%Y-%m-%d", time.localtime())
