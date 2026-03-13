from __future__ import annotations

import ctypes
from dataclasses import dataclass

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore[assignment]


@dataclass(slots=True)
class ActiveWindowContext:
    title: str
    pid: int | None = None
    process_name: str | None = None
    executable_name: str | None = None


def get_active_window_context() -> ActiveWindowContext:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ActiveWindowContext(title="")
    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length > 0:
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()

    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_value = int(pid.value) if pid.value else None
    process_name = None
    executable_name = None

    if pid_value and psutil is not None:
        try:
            process = psutil.Process(pid_value)
            process_name = process.name()
            executable_name = process.exe().split("\\")[-1]
        except Exception:
            pass

    return ActiveWindowContext(
        title=title,
        pid=pid_value,
        process_name=process_name,
        executable_name=executable_name,
    )


def is_blocked_title(active_title: str, blocked_tokens: list[str]) -> bool:
    title = active_title.strip().lower()
    if not title:
        return False
    return any(token in title for token in blocked_tokens)
