from __future__ import annotations

import re
from dataclasses import dataclass

from screensense.models import VisionDecision


@dataclass(slots=True)
class ImpactDecision:
    score: float
    allow_interrupt: bool
    reason: str


class ImpactScorer:
    def __init__(self, *, enabled: bool, threshold: float) -> None:
        self._enabled = enabled
        self._threshold = max(0.0, min(1.0, threshold))

    def evaluate(
        self,
        *,
        decision: VisionDecision,
        changed_percent: float,
        user_idle: bool,
        away: bool,
        session_minutes: int,
        inference_source: str = "",
        threshold_override: float | None = None,
    ) -> ImpactDecision:
        threshold = self._threshold if threshold_override is None else max(0.0, min(1.0, threshold_override))
        if not self._enabled:
            return ImpactDecision(score=1.0, allow_interrupt=True, reason="impact_scoring_disabled")

        score = 0.0
        score += decision.confidence * 0.45
        score += self._priority_weight(decision.priority)
        score += 0.10 if decision.can_fix else 0.0
        score += 0.06 if away else 0.0
        score += 0.06 if user_idle else -0.12
        score += self._motion_weight(changed_percent)
        score += 0.05 if decision.domain == "code" and decision.can_fix else 0.0
        score += 0.04 if session_minutes >= 90 and decision.priority == "critical" else 0.0
        score += self._message_urgency_weight(decision.message)
        if inference_source.startswith("local"):
            score += 0.06
        if not decision.should_interrupt:
            score -= 0.25

        score = max(0.0, min(1.0, score))
        if score < threshold:
            return ImpactDecision(
                score=score,
                allow_interrupt=False,
                reason="impact_below_threshold",
            )
        return ImpactDecision(score=score, allow_interrupt=True, reason="impact_passed")

    @staticmethod
    def _priority_weight(priority: str) -> float:
        if priority == "critical":
            return 0.28
        if priority == "helpful":
            return 0.12
        return -0.25

    @staticmethod
    def _motion_weight(changed_percent: float) -> float:
        if changed_percent >= 40:
            return 0.08
        if changed_percent >= 20:
            return 0.04
        if changed_percent <= 3:
            return -0.02
        return 0.0

    @staticmethod
    def _message_urgency_weight(message: str) -> float:
        normalized = re.sub(r"\s+", " ", message.strip().lower())
        urgent_tokens = ("error", "exception", "failed", "crash", "quota", "denied", "blocked")
        if any(token in normalized for token in urgent_tokens):
            return 0.05
        return 0.0
