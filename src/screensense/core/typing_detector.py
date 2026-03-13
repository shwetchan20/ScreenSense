from __future__ import annotations

import time
from threading import Lock

import keyboard


class TypingDetector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._last_keypress_ts = 0.0
        keyboard.on_press(self._on_press, suppress=False)

    def _on_press(self, _event: keyboard.KeyboardEvent) -> None:
        with self._lock:
            self._last_keypress_ts = time.time()

    def is_idle(self, idle_seconds: float) -> bool:
        with self._lock:
            last = self._last_keypress_ts
        if last == 0.0:
            return True
        return (time.time() - last) >= idle_seconds

    def seconds_since_last_keypress(self) -> float:
        with self._lock:
            last = self._last_keypress_ts
        if last == 0.0:
            return 1e9
        return max(0.0, time.time() - last)
