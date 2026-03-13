from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from screensense.models import VisionDecision


@dataclass(slots=True)
class InterruptDecision:
    allow_interrupt: bool
    score: float
    reason: str
    impact: float
    urgency: float
    receptivity: float


class InterruptBrain:
    def __init__(self) -> None:
        self._interrupt_history: deque[float] = deque()
        self._rejection_history: deque[float] = deque()
        self._consecutive_rejections = 0
        self._quiet_until_ts = 0.0
        self._last_interrupt_ts = 0.0

    def evaluate(
        self,
        *,
        decision: VisionDecision,
        confidence: float,
        typing_seconds_since: float,
        session_minutes: int,
    ) -> InterruptDecision:
        now = time.time()
        if now < self._quiet_until_ts:
            return InterruptDecision(
                allow_interrupt=False,
                score=0.0,
                reason="quiet_mode_active",
                impact=0.0,
                urgency=0.0,
                receptivity=0.0,
            )
        if decision.priority == "silent":
            return InterruptDecision(False, 0.0, "priority_silent", 0.0, 0.0, 0.0)
        if not decision.should_interrupt:
            return InterruptDecision(False, 0.0, "model_said_no", 0.0, 0.0, 0.0)
        if typing_seconds_since < 5 and decision.priority != "critical":
            return InterruptDecision(False, 0.0, "typing_active", 0.0, 0.0, 0.0)

        self._evict_old(self._interrupt_history, now, window_seconds=3600)
        self._evict_old(self._rejection_history, now, window_seconds=3600)
        if len(self._interrupt_history) >= 8:
            return InterruptDecision(False, 0.0, "interrupt_budget_exhausted", 0.0, 0.0, 0.0)
        if self._count_last(self._interrupt_history, now, window_seconds=600) >= 2:
            return InterruptDecision(False, 0.0, "ten_minute_budget_exhausted", 0.0, 0.0, 0.0)

        impact = self._impact_score(decision)
        urgency = self._urgency_score(decision)
        receptivity = self._receptivity_score(
            typing_seconds_since=typing_seconds_since,
            rejection_count=len(self._rejection_history),
            session_minutes=session_minutes,
        )
        score = (
            (impact * 0.35)
            + (confidence * 0.25)
            + (urgency * 0.20)
            + (receptivity * 0.20)
        )

        threshold = 0.65
        if (now - self._last_interrupt_ts) > (20 * 60):
            threshold = 0.80
        if score < threshold:
            return InterruptDecision(
                allow_interrupt=False,
                score=score,
                reason="interrupt_score_below_threshold",
                impact=impact,
                urgency=urgency,
                receptivity=receptivity,
            )
        return InterruptDecision(True, score, "interrupt_score_passed", impact, urgency, receptivity)

    def record_interrupt(self) -> None:
        now = time.time()
        self._interrupt_history.append(now)
        self._last_interrupt_ts = now

    def record_rejection(self) -> None:
        now = time.time()
        self._rejection_history.append(now)
        self._consecutive_rejections += 1
        if self._consecutive_rejections >= 3:
            self._quiet_until_ts = now + (30 * 60)
            self._consecutive_rejections = 0

    def record_accept(self) -> None:
        self._consecutive_rejections = 0

    @staticmethod
    def _impact_score(decision: VisionDecision) -> float:
        if decision.priority == "critical":
            return 1.0
        normalized = _normalize(decision.message)
        if any(token in normalized for token in ("error", "exception", "failed", "crash")):
            return 0.8
        if any(token in normalized for token in ("warning", "warn")):
            return 0.6
        if decision.priority == "helpful":
            return 0.4
        return 0.2

    @staticmethod
    def _urgency_score(decision: VisionDecision) -> float:
        normalized = _normalize(decision.message)
        if any(token in normalized for token in ("data loss", "overwrite", "deleted", "critical")):
            return 1.0
        if any(token in normalized for token in ("build failed", "tests failing", "compile error")):
            return 0.9
        if any(token in normalized for token in ("quota", "rate limit", "limit")):
            return 0.8
        if any(token in normalized for token in ("unsaved", "dirty", "uncommitted")):
            return 0.7
        return 0.3

    @staticmethod
    def _receptivity_score(
        *,
        typing_seconds_since: float,
        rejection_count: int,
        session_minutes: int,
    ) -> float:
        if typing_seconds_since < 5:
            typing_score = 0.1
        elif typing_seconds_since < 30:
            typing_score = 0.5
        else:
            typing_score = 0.9

        if rejection_count <= 0:
            rejection_score = 0.8
        elif rejection_count == 1:
            rejection_score = 0.6
        elif rejection_count == 2:
            rejection_score = 0.45
        else:
            rejection_score = 0.3

        hour = datetime.now().hour
        time_score = 0.4 if 0 <= hour < 6 else 1.0

        if session_minutes > 180:
            session_score = 0.7
        elif session_minutes >= 60:
            session_score = 1.0
        else:
            session_score = 0.9

        return max(0.0, min(1.0, (typing_score + rejection_score + time_score + session_score) / 4))

    @staticmethod
    def _evict_old(queue: deque[float], now: float, window_seconds: int) -> None:
        while queue and (now - queue[0]) > window_seconds:
            queue.popleft()

    @staticmethod
    def _count_last(queue: deque[float], now: float, window_seconds: int) -> int:
        return sum(1 for ts in queue if (now - ts) <= window_seconds)


def _normalize(text: str) -> str:
    clean = re.sub(r"[^a-z0-9\\s]+", " ", text.lower())
    return re.sub(r"\\s+", " ", clean).strip()
