from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import requests
import subprocess


@dataclass(slots=True)
class HealthStatus:
    local_llm_ok: bool = True
    gemini_ok: bool = True
    gemini_quota_exhausted: bool = False
    ui_automation_ok: bool = True
    tts_ok: bool = True
    telegram_ok: bool = True
    browser_ok: bool = True
    safe_mode: bool = False


class HealthMonitor:
    def __init__(
        self,
        *,
        notify_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self._status = HealthStatus()
        self._notify = notify_callback
        self._last_ping_ts = 0.0
        self._last_notified: dict[str, float] = {}
        self._ping_interval_seconds = 60.0

    def status(self) -> HealthStatus:
        return self._status

    def ping_local_llm(self, base_url: str) -> bool:
        now = time.time()
        if (now - self._last_ping_ts) < self._ping_interval_seconds:
            return self._status.local_llm_ok
        self._last_ping_ts = now
        try:
            response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=4)
            ok = response.status_code < 500
        except Exception:
            ok = False
        self._status.local_llm_ok = ok
        if not ok:
            self._notify_once("local_llm_offline", "local model offline. cloud only.")
        return ok

    def kill_local_llm(self) -> None:
        subprocess.run(
            ["taskkill", "/F", "/IM", "ollama.exe"],
            capture_output=True,
        )
        self._status.local_llm_ok = False

    def set_gemini_state(self, ok: bool, quota_exhausted: bool = False) -> None:
        self._status.gemini_ok = ok
        self._status.gemini_quota_exhausted = quota_exhausted
        if quota_exhausted:
            self._notify_once("gemini_quota", "cloud quota gone. local only.")

    def note_ui_automation(self, ok: bool) -> None:
        self._status.ui_automation_ok = ok
        if not ok:
            self._notify_once("ui_automation_down", "ui automation unavailable. using ocr.")

    def note_tts_failure(self) -> None:
        self._status.tts_ok = False
        self._notify_once("tts_down", "tts unavailable. using notifications.")

    def note_telegram(self, ok: bool) -> None:
        self._status.telegram_ok = ok

    def note_browser(self, ok: bool) -> None:
        self._status.browser_ok = ok

    def evaluate_fallbacks(self) -> dict[str, object]:
        if not self._status.local_llm_ok and not self._status.gemini_ok:
            self._status.safe_mode = True
            return {"safe_mode": True, "reasoning_mode": "none", "disable_vision": True}
        if not self._status.local_llm_ok and self._status.gemini_ok:
            return {"safe_mode": False, "reasoning_mode": "gemini", "disable_vision": False}
        if self._status.gemini_quota_exhausted:
            return {"safe_mode": False, "reasoning_mode": "local", "disable_vision": True}
        return {"safe_mode": False, "reasoning_mode": "hybrid", "disable_vision": False}

    def status_summary(self) -> str:
        parts = [
            f"local_llm={'ok' if self._status.local_llm_ok else 'down'}",
            f"gemini={'ok' if self._status.gemini_ok else 'down'}",
            f"ui_automation={'ok' if self._status.ui_automation_ok else 'down'}",
            f"tts={'ok' if self._status.tts_ok else 'down'}",
            f"telegram={'ok' if self._status.telegram_ok else 'down'}",
            f"browser={'ok' if self._status.browser_ok else 'down'}",
            f"safe_mode={'on' if self._status.safe_mode else 'off'}",
        ]
        return "health: " + ", ".join(parts)

    def _notify_once(self, key: str, message: str) -> None:
        now = time.time()
        if (now - self._last_notified.get(key, 0.0)) < 300:
            return
        self._last_notified[key] = now
        if self._notify is None:
            return
        try:
            self._notify("ScreenSense", message)
        except Exception:
            return
