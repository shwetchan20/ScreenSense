from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class RateGuardDecision:
    allowed: bool
    reason: str
    retry_after_seconds: float = 0.0


class GeminiRateGuard:
    def __init__(self, min_interval_seconds: float, max_calls_per_minute: int) -> None:
        self._min_interval_seconds = max(0.0, min_interval_seconds)
        self._max_calls_per_minute = max(1, max_calls_per_minute)
        self._last_call_ts = 0.0
        self._calls_last_minute: deque[float] = deque()

    def check(self) -> RateGuardDecision:
        now = time.time()
        self._evict_old(now)

        if self._last_call_ts > 0:
            elapsed = now - self._last_call_ts
            if elapsed < self._min_interval_seconds:
                return RateGuardDecision(
                    allowed=False,
                    reason="min_interval_guard",
                    retry_after_seconds=round(self._min_interval_seconds - elapsed, 2),
                )

        if len(self._calls_last_minute) >= self._max_calls_per_minute:
            retry_after = 60.0 - (now - self._calls_last_minute[0])
            return RateGuardDecision(
                allowed=False,
                reason="max_calls_per_minute_guard",
                retry_after_seconds=round(max(1.0, retry_after), 2),
            )

        self._last_call_ts = now
        self._calls_last_minute.append(now)
        return RateGuardDecision(allowed=True, reason="allowed")

    def _evict_old(self, now: float) -> None:
        while self._calls_last_minute and (now - self._calls_last_minute[0]) >= 60.0:
            self._calls_last_minute.popleft()

