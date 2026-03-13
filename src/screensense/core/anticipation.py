from __future__ import annotations

import time


class AnticipationEngine:
    def __init__(self) -> None:
        self._last_quota_nudge_ts = 0.0
        self._last_network_nudge_ts = 0.0
        self._last_motion_nudge_ts = 0.0
        self._high_motion_streak = 0

    def note_motion(self, changed_percent: float) -> str | None:
        if changed_percent >= 70.0:
            self._high_motion_streak += 1
        else:
            self._high_motion_streak = 0
        if self._high_motion_streak < 3:
            return None
        now = time.time()
        if (now - self._last_motion_nudge_ts) < 300:
            return None
        self._last_motion_nudge_ts = now
        return (
            "High-motion screen detected for multiple cycles. "
            "If this is a game or video, add the app title to blocklist to avoid wasted calls."
        )

    def nudge_for_error(self, exc: Exception) -> str | None:
        text = str(exc).lower()
        now = time.time()
        if "quota exceeded" in text or "resource_exhausted" in text:
            if (now - self._last_quota_nudge_ts) < 900:
                return None
            self._last_quota_nudge_ts = now
            return (
                "Quota is exhausted. I will keep monitoring locally and defer AI calls until quota resets."
            )
        if "timed out" in text or "connection" in text or "unavailable" in text:
            if (now - self._last_network_nudge_ts) < 300:
                return None
            self._last_network_nudge_ts = now
            return "Network looks unstable. I will retry with backoff and keep audit logs complete."
        return None
