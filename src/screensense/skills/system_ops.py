from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable

from screensense.core.action_gate import ActionGate

try:
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None  # type: ignore[assignment]

try:
    from win10toast import ToastNotifier
except Exception:  # pragma: no cover
    ToastNotifier = None  # type: ignore[assignment]


class SystemOps:
    def __init__(
        self,
        action_gate: ActionGate | None = None,
        speak_callback: Callable[[str], None] | None = None,
        notify_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self._gate = action_gate
        self._speak = speak_callback
        self._notify = notify_callback
        self._toaster = ToastNotifier() if ToastNotifier is not None else None

    def copy_to_clipboard(self, text: str) -> bool:
        if not self._approve("copy_to_clipboard", "low"):
            return False
        if pyperclip is None:
            return False
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def open_application(self, name: str) -> bool:
        if not self._approve(f"open_application {name}", "low"):
            return False
        try:
            if os.path.exists(name):
                os.startfile(name)  # type: ignore[attr-defined]
                return True
            subprocess.Popen([name], shell=True)
            return True
        except Exception:
            return False

    def show_notification(self, title: str, body: str) -> bool:
        if not self._approve("show_notification", "low"):
            return False
        if self._notify is not None:
            try:
                self._notify(title, body)
                return True
            except Exception:
                return False
        if self._toaster is None:
            return False
        try:
            self._toaster.show_toast(title, body, duration=4, threaded=True)
            return True
        except Exception:
            return False

    def set_reminder(self, minutes: int, message: str) -> bool:
        if not self._approve(f"set_reminder {minutes}m", "low"):
            return False
        delay = max(1, int(minutes)) * 60

        def fire() -> None:
            if self._speak is not None:
                try:
                    self._speak(message)
                except Exception:
                    pass
            self.show_notification("Reminder", message)

        threading.Timer(delay, fire).start()
        return True

    def _approve(self, preview: str, risk: str) -> bool:
        if self._gate is None:
            return False
        return self._gate.approve(preview, risk)
