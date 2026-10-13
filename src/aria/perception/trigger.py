from __future__ import annotations

import asyncio
import io
import time
from dataclasses import dataclass
from typing import Any

import mss
import numpy as np
import win32gui
from PIL import Image
from pynput import keyboard, mouse


@dataclass(slots=True)
class TriggerEvent:
    source: str
    user_task: str = ""
    created_at: float = 0.0
    response_future: asyncio.Future[str] | None = None


class TriggerSystem:
    def __init__(self, *, queue: asyncio.Queue[TriggerEvent]) -> None:
        self._queue = queue
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None
        self._window_watcher_task: asyncio.Task[None] | None = None
        self._diff_watcher_task: asyncio.Task[None] | None = None
        self._last_hwnd: int | None = None
        self._last_frame: np.ndarray | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._keyboard_listener = keyboard.Listener(on_press=self._on_press)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        self._window_watcher_task = asyncio.create_task(self._watch_active_window())
        self._diff_watcher_task = asyncio.create_task(self._watch_pixel_diff())

    async def stop(self) -> None:
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
        if self._window_watcher_task is not None:
            self._window_watcher_task.cancel()
        if self._diff_watcher_task is not None:
            self._diff_watcher_task.cancel()

    async def enqueue(self, source: str, user_task: str = "", future: asyncio.Future[str] | None = None) -> None:
        await self._queue.put(
            TriggerEvent(
                source=source,
                user_task=user_task,
                created_at=time.time(),
                response_future=future,
            )
        )

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed or self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            self._queue.put_nowait,
            TriggerEvent(source="mouse_click", created_at=time.time()),
        )

    def _on_press(self, key: Any) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(
            self._queue.put_nowait,
            TriggerEvent(source="keyboard", created_at=time.time()),
        )

    async def _watch_active_window(self) -> None:
        while True:
            hwnd = await asyncio.get_running_loop().run_in_executor(None, win32gui.GetForegroundWindow)
            if self._last_hwnd is None:
                self._last_hwnd = hwnd
            if hwnd != self._last_hwnd:
                self._last_hwnd = hwnd
                await self.enqueue("window_change")
            await asyncio.sleep(0.5)

    async def _watch_pixel_diff(self) -> None:
        while True:
            frame = await asyncio.get_running_loop().run_in_executor(None, _capture_np_frame)
            if self._last_frame is None:
                self._last_frame = frame
            else:
                diff = _diff_percent(self._last_frame, frame)
                self._last_frame = frame
                if diff > 5.0:
                    await self.enqueue("pixel_diff")
            await asyncio.sleep(0.8)


def _capture_np_frame() -> np.ndarray:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        pil = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        arr = np.array(pil)
        return arr


def _diff_percent(prev: np.ndarray, curr: np.ndarray) -> float:
    if prev.shape != curr.shape:
        return 100.0
    delta = np.abs(prev.astype(np.int16) - curr.astype(np.int16))
    changed = np.count_nonzero(np.any(delta > 10, axis=2))
    total = prev.shape[0] * prev.shape[1]
    return (changed / total) * 100.0
