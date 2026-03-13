from __future__ import annotations

import numpy as np

from screensense.core.ui_context import UiContextExtractor
from screensense.integrations.gemini_client import GeminiVisionClient
from screensense.models import VisionDecision


class LocalGeminiInferenceClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        ui_context_extractor: UiContextExtractor | None = None,
    ) -> None:
        self._vision = GeminiVisionClient(api_key=api_key, model=model)
        self._ui_context_extractor = ui_context_extractor
        self.last_source = "gemini_local"

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        context = app_context or {}
        if self._ui_context_extractor is not None:
            context = self._ui_context_extractor.enrich(frame_rgb=frame_rgb, app_context=context)
        return self._vision.analyze(frame_rgb, app_context=context)
