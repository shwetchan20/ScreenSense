from __future__ import annotations

from screensense.inference.contracts import AnalyzeRequest, AnalyzeResponse
from screensense.inference.image_codec import decode_png_base64
from screensense.integrations.gemini_client import GeminiVisionClient


class BackendInferenceService:
    def __init__(self, api_key: str, model: str) -> None:
        self._vision = GeminiVisionClient(api_key=api_key, model=model)

    def analyze(self, req: AnalyzeRequest) -> AnalyzeResponse:
        frame_rgb = decode_png_base64(req.screenshot_png_base64)
        decision = self._vision.analyze(frame_rgb=frame_rgb, app_context=req.app_context)
        return AnalyzeResponse(decision=decision)

