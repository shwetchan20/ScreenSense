from __future__ import annotations

import threading
import time
from typing import Callable, Iterable

try:
    import keyboard  # type: ignore
except Exception:  # pragma: no cover
    keyboard = None  # type: ignore[assignment]


class ActionGate:
    def __init__(
        self,
        *,
        allowlist: Iterable[str],
        telegram_request_approval: Callable[[str, float], bool | None] | None = None,
        whisper_callback: Callable[[str], None] | None = None,
        log_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._allowlist = {item.strip().lower() for item in allowlist if item.strip()}
        self._telegram_request_approval = telegram_request_approval
        self._whisper_callback = whisper_callback
        self._log_callback = log_callback

    def request_approval(
        self,
        action_fn: Callable[[], bool | str],
        preview: str,
        risk: str,
    ) -> bool:
        approved = self.approve(preview, risk)
        return self._handle_decision(approved, action_fn, preview, risk)

    def approve(self, preview: str, risk: str) -> bool:
        risk = (risk or "low").strip().lower()
        if risk == "low" and self._is_allowlisted(preview):
            self._log("action_auto_allowed", {"preview": preview, "risk": risk})
            return True
        if risk == "medium":
            self._send_whisper(f"{preview} — do it?")
            approved = self._await_approval(timeout_seconds=15)
            return approved is True
        if risk == "high":
            self._send_whisper("needs your approval in Telegram")
            approved = self._await_approval(timeout_seconds=60)
            return approved is True
        approved = self._await_approval(timeout_seconds=15)
        return approved is True

    def _is_allowlisted(self, preview: str) -> bool:
        lowered = preview.lower()
        return any(token in lowered for token in self._allowlist)

    def _handle_decision(
        self,
        approved: bool,
        action_fn: Callable[[], bool | str],
        preview: str,
        risk: str,
    ) -> bool:
        if approved:
            result = self._execute(action_fn)
            self._log("action_approved", {"preview": preview, "risk": risk, "result": result})
            return True
        self._log("action_rejected", {"preview": preview, "risk": risk})
        return False

    def _execute(self, action_fn: Callable[[], bool | str]) -> bool:
        try:
            result = action_fn()
        except Exception:
            return False
        if isinstance(result, bool):
            return result
        return True

    def _await_approval(self, *, timeout_seconds: float) -> bool | None:
        telegram_result = None
        if self._telegram_request_approval is not None:
            telegram_result = self._telegram_request_approval(
                "Approval required. Reply with the buttons.",
                timeout_seconds,
            )
            if telegram_result is not None:
                return telegram_result
        keyboard_result = self._wait_for_keyboard(timeout_seconds)
        return keyboard_result

    def _wait_for_keyboard(self, timeout_seconds: float) -> bool | None:
        if keyboard is None:
            return None
        event = threading.Event()
        decision: dict[str, bool] = {}

        def on_press(e) -> None:  # pragma: no cover
            key = getattr(e, "name", "").lower()
            if key == "y":
                decision["value"] = True
                event.set()
            if key == "n":
                decision["value"] = False
                event.set()

        hook = keyboard.on_press(on_press)
        try:
            event.wait(timeout_seconds)
        finally:
            keyboard.unhook(hook)
        return decision.get("value")

    def _send_whisper(self, message: str) -> None:
        if self._whisper_callback is None:
            return
        try:
            self._whisper_callback(message)
        except Exception:
            return

    def _log(self, event: str, payload: dict) -> None:
        if self._log_callback is None:
            return
        try:
            self._log_callback(event, payload)
        except Exception:
            return
