from __future__ import annotations

import numpy as np
from mss import mss


class ScreenCapturer:
    def __init__(self) -> None:
        self._sct = mss()
        self._monitor = self._sct.monitors[1]

    def capture_rgb(self) -> np.ndarray:
        shot = self._sct.grab(self._monitor)
        bgra = np.array(shot, dtype=np.uint8)
        return bgra[:, :, :3][:, :, ::-1]

