from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class CircuitDecision:
    allow: bool
    reason: str
    retry_after_seconds: float = 0.0


class VisionCircuitBreaker:
    def __init__(
        self,
        error_threshold: int,
        error_window_seconds: float,
        open_duration_seconds: float,
    ) -> None:
        self._error_threshold = max(1, error_threshold)
        self._error_window_seconds = max(1.0, error_window_seconds)
        self._open_duration_seconds = max(1.0, open_duration_seconds)
        self._error_timestamps: deque[float] = deque()
        self._open_until_ts = 0.0

    def check(self) -> CircuitDecision:
        now = time.time()
        if now < self._open_until_ts:
            return CircuitDecision(
                allow=False,
                reason="vision_circuit_open",
                retry_after_seconds=round(self._open_until_ts - now, 2),
            )
        return CircuitDecision(allow=True, reason="closed")

    def record_error(self) -> CircuitDecision:
        now = time.time()
        self._evict_old(now)
        self._error_timestamps.append(now)
        if len(self._error_timestamps) >= self._error_threshold:
            self._open_until_ts = now + self._open_duration_seconds
            self._error_timestamps.clear()
            return CircuitDecision(
                allow=False,
                reason="vision_circuit_opened",
                retry_after_seconds=round(self._open_duration_seconds, 2),
            )
        return CircuitDecision(allow=True, reason="error_recorded")

    def record_success(self) -> None:
        self._error_timestamps.clear()

    def _evict_old(self, now: float) -> None:
        while self._error_timestamps and (now - self._error_timestamps[0]) > self._error_window_seconds:
            self._error_timestamps.popleft()

