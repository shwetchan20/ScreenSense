from __future__ import annotations

from typing import Protocol

import numpy as np

from screensense.models import VisionDecision


class InferenceClient(Protocol):
    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        ...
