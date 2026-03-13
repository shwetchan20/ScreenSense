from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from screensense.models import VisionDecision


@dataclass(slots=True)
class PresenceSnapshot:
    now_iso: str
    weekday: str
    time_block: str
    session_minutes: int
    session_start_iso: str
    away: bool
    goal: str
    deadline_days_left: int | None
    memory_digest: str


class PresenceEngine:
    def __init__(
        self,
        *,
        assistant_name: str,
        assistant_persona: str,
        user_name: str,
        project_name: str,
        deadline_date: str,
        away_idle_seconds: float,
        break_nudge_minutes: float,
        break_nudge_repeat_minutes: float,
    ) -> None:
        self._assistant_name = assistant_name.strip() or "ARIA"
        self._assistant_persona = assistant_persona.strip() or "calm concise proactive with dry wit"
        self._user_name = user_name.strip() or "Operator"
        self._project_name = project_name.strip() or "ScreenSense"
        self._deadline_date = deadline_date.strip()
        self._away_idle_seconds = max(60.0, away_idle_seconds)
        self._break_nudge_minutes = max(15.0, break_nudge_minutes)
        self._break_nudge_repeat_minutes = max(15.0, break_nudge_repeat_minutes)
        now = time.time()
        self._session_start_ts = now
        self._last_activity_ts = now
        self._last_break_nudge_ts = 0.0

    def update_activity(self, *, user_idle: bool, changed_percent: float) -> None:
        if not user_idle or changed_percent >= 0.5:
            self._last_activity_ts = time.time()

    def snapshot(self, *, goal: str, memory_digest: str) -> PresenceSnapshot:
        now = datetime.now()
        return PresenceSnapshot(
            now_iso=now.isoformat(timespec="seconds"),
            weekday=now.strftime("%A"),
            time_block=self._time_block(now.hour),
            session_minutes=int((time.time() - self._session_start_ts) // 60),
            session_start_iso=datetime.fromtimestamp(self._session_start_ts).isoformat(timespec="seconds"),
            away=self.is_away(),
            goal=goal,
            deadline_days_left=self._deadline_days_left(now),
            memory_digest=memory_digest,
        )

    def is_away(self) -> bool:
        return (time.time() - self._last_activity_ts) >= self._away_idle_seconds

    def maybe_break_nudge(self, *, user_idle: bool) -> str | None:
        if not user_idle:
            return None
        session_minutes = int((time.time() - self._session_start_ts) // 60)
        if session_minutes < int(self._break_nudge_minutes):
            return None
        now = time.time()
        if (now - self._last_break_nudge_ts) < (self._break_nudge_repeat_minutes * 60):
            return None
        self._last_break_nudge_ts = now
        return (
            f"{self._user_name}, you've been focused for {session_minutes} minutes. "
            "Take a quick break and hydrate, then we'll continue."
        )

    def compose_spoken_message(self, decision: VisionDecision, *, goal: str) -> str:
        base = decision.message.strip()
        if not base:
            return ""
        if decision.priority == "critical":
            lead = "Important update"
        elif decision.priority == "helpful":
            lead = "Heads up"
        else:
            lead = "Quick note"
        return (
            f"{self._user_name}, {lead}. {base} "
            f"Current objective: {goal}."
        ).strip()

    def to_inference_context(self, snapshot: PresenceSnapshot) -> dict[str, str | int | bool]:
        context: dict[str, str | int | bool] = {
            "assistant_name": self._assistant_name,
            "assistant_persona": self._assistant_persona,
            "user_name": self._user_name,
            "project_name": self._project_name,
            "now_iso": snapshot.now_iso,
            "weekday": snapshot.weekday,
            "time_block": snapshot.time_block,
            "session_minutes": snapshot.session_minutes,
            "session_start_iso": snapshot.session_start_iso,
            "away": snapshot.away,
            "goal": snapshot.goal,
            "memory_digest": snapshot.memory_digest,
        }
        if snapshot.deadline_days_left is not None:
            context["deadline_days_left"] = snapshot.deadline_days_left
        return context

    @staticmethod
    def load_memory_digest(path: str, *, max_lines: int = 80) -> str:
        file_path = Path(path)
        if not file_path.exists():
            return "none"
        lines: list[str] = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
        if not lines:
            return "none"
        recent = lines[-max_lines:]
        contexts: dict[str, int] = {}
        for raw in recent:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            decision = record.get("decision") or {}
            context = str(decision.get("context") or "unknown").strip().lower()
            if not context:
                continue
            contexts[context] = contexts.get(context, 0) + 1
        if not contexts:
            return "none"
        top = sorted(contexts.items(), key=lambda item: item[1], reverse=True)[:3]
        return ", ".join(f"{name}:{count}" for name, count in top)

    @staticmethod
    def _time_block(hour: int) -> str:
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 22:
            return "evening"
        return "late_night"

    def _deadline_days_left(self, now: datetime) -> int | None:
        if not self._deadline_date:
            return None
        try:
            deadline = datetime.fromisoformat(self._deadline_date).date()
        except ValueError:
            return None
        return (deadline - now.date()).days
