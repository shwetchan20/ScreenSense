from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime
from dataclasses import dataclass
from collections import deque

from screensense.models import VisionDecision


@dataclass(slots=True)
class PolicyDecision:
    allow_interrupt: bool
    reason: str


class InterruptPolicy:
    def __init__(
        self,
        confidence_threshold: float,
        interrupt_cooldown_seconds: float,
        dedupe_window_seconds: float,
        semantic_dedupe_window_seconds: float = 0.0,
        max_interrupts_per_hour: int = 8,
        quiet_hours_start: int = -1,
        quiet_hours_end: int = -1,
    ) -> None:
        self._confidence_threshold = confidence_threshold
        self._interrupt_cooldown_seconds = interrupt_cooldown_seconds
        self._dedupe_window_seconds = dedupe_window_seconds
        self._semantic_dedupe_window_seconds = semantic_dedupe_window_seconds
        self._max_interrupts_per_hour = max(1, max_interrupts_per_hour)
        self._quiet_hours_start = quiet_hours_start
        self._quiet_hours_end = quiet_hours_end
        self._last_interrupt_ts = 0.0
        self._last_seen_by_fingerprint: dict[str, float] = {}
        self._last_seen_by_semantic_fingerprint: dict[str, float] = {}
        self._interrupt_history: deque[float] = deque()

    def evaluate(self, decision: VisionDecision, user_idle: bool) -> PolicyDecision:
        now = time.time()
        if decision.priority == "silent":
            return PolicyDecision(False, "priority_silent")
        if not decision.should_interrupt:
            return PolicyDecision(False, "model_said_no")
        if decision.confidence < self._confidence_threshold:
            return PolicyDecision(False, "low_confidence")
        if not user_idle:
            return PolicyDecision(False, "user_active")
        if self._in_quiet_hours() and decision.priority != "critical":
            return PolicyDecision(False, "quiet_hours")
        self._evict_old_interrupts(now)
        if len(self._interrupt_history) >= self._max_interrupts_per_hour:
            return PolicyDecision(False, "interrupt_budget_exhausted")
        if (now - self._last_interrupt_ts) < self._interrupt_cooldown_seconds:
            return PolicyDecision(False, "global_cooldown")

        fingerprint = self._fingerprint(decision)
        last_seen = self._last_seen_by_fingerprint.get(fingerprint, 0.0)
        if (now - last_seen) < self._dedupe_window_seconds:
            return PolicyDecision(False, "duplicate_suppressed")

        semantic_fingerprint = self._semantic_fingerprint(decision)
        semantic_last_seen = self._last_seen_by_semantic_fingerprint.get(semantic_fingerprint, 0.0)
        if self._semantic_dedupe_window_seconds > 0 and (
            (now - semantic_last_seen) < self._semantic_dedupe_window_seconds
        ):
            return PolicyDecision(False, "semantic_duplicate_suppressed")

        self._last_interrupt_ts = now
        self._interrupt_history.append(now)
        self._last_seen_by_fingerprint[fingerprint] = now
        self._last_seen_by_semantic_fingerprint[semantic_fingerprint] = now
        self._evict_old_fingerprints(now)
        return PolicyDecision(True, "allowed")

    def _evict_old_interrupts(self, now: float) -> None:
        while self._interrupt_history and (now - self._interrupt_history[0]) > 3600:
            self._interrupt_history.popleft()

    def _evict_old_fingerprints(self, now: float) -> None:
        keys = [
            key
            for key, ts in self._last_seen_by_fingerprint.items()
            if (now - ts) > self._dedupe_window_seconds
        ]
        for key in keys:
            del self._last_seen_by_fingerprint[key]
        if self._semantic_dedupe_window_seconds <= 0:
            return
        semantic_keys = [
            key
            for key, ts in self._last_seen_by_semantic_fingerprint.items()
            if (now - ts) > self._semantic_dedupe_window_seconds
        ]
        for key in semantic_keys:
            del self._last_seen_by_semantic_fingerprint[key]

    @staticmethod
    def _fingerprint(decision: VisionDecision) -> str:
        material = f"{decision.context}|{decision.domain}|{decision.message}".strip().lower()
        return hashlib.sha1(material.encode("utf-8")).hexdigest()

    @classmethod
    def _semantic_fingerprint(cls, decision: VisionDecision) -> str:
        normalized_context = cls._normalize_text(decision.context)
        intent = cls._message_intent(decision.message)
        material = f"{decision.domain}|{normalized_context}|{intent}"
        return hashlib.sha1(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_text(text: str) -> str:
        clean = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return re.sub(r"\s+", " ", clean).strip()

    @classmethod
    def _message_intent(cls, message: str) -> str:
        normalized = cls._normalize_text(message)
        if any(term in normalized for term in ("code review", "proposed changes", "review carefully")):
            return "code_review_warning"
        if any(term in normalized for term in ("hackathon team", "female member", "teammate")):
            return "team_formation"
        if any(term in normalized for term in ("summarize", "github repository", "agent s")):
            return "repo_summary_offer"
        tokens = normalized.split()
        return "generic:" + " ".join(tokens[:6])

    def _in_quiet_hours(self) -> bool:
        start = self._quiet_hours_start
        end = self._quiet_hours_end
        if not (0 <= start <= 23 and 0 <= end <= 23):
            return False
        hour = datetime.now().hour
        if start == end:
            return True
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end
