from __future__ import annotations

import time


class FastPathGate:
    def __init__(
        self,
        *,
        enabled: bool,
        user_active_diff_max: float,
        app_revisit_seconds: float,
        app_revisit_diff_max: float,
    ) -> None:
        self._enabled = enabled
        self._user_active_diff_max = max(0.0, user_active_diff_max)
        self._app_revisit_seconds = max(0.0, app_revisit_seconds)
        self._app_revisit_diff_max = max(0.0, app_revisit_diff_max)
        self._last_app = ""
        self._last_inference_ts = 0.0

    def should_skip(
        self,
        *,
        user_idle: bool,
        changed_percent: float,
        app_key: str,
    ) -> str | None:
        if not self._enabled:
            return None
        now = time.time()
        normalized_app = app_key.strip().lower()

        if not user_idle and changed_percent <= self._user_active_diff_max:
            return "fast_path_user_active_low_signal"

        same_app_recent = (
            normalized_app
            and normalized_app == self._last_app
            and (now - self._last_inference_ts) < self._app_revisit_seconds
            and changed_percent <= self._app_revisit_diff_max
        )
        if same_app_recent:
            return "fast_path_same_app_revisit"
        return None

    def note_inference_submitted(self, app_key: str) -> None:
        self._last_app = app_key.strip().lower()
        self._last_inference_ts = time.time()
