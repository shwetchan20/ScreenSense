from __future__ import annotations

import requests
import numpy as np

from screensense.inference.contracts import AnalyzeRequest, AnalyzeResponse
from screensense.inference.image_codec import encode_png_base64
from screensense.models import VisionDecision


class HttpInferenceClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 30.0,
        auth_token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._auth_token = (auth_token or "").strip()
        self.last_source = "gemini_http"

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        payload = AnalyzeRequest(
            screenshot_png_base64=encode_png_base64(frame_rgb),
            app_context=app_context or {},
        ).model_dump()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        response = requests.post(
            f"{self._base_url}/analyze",
            json=payload,
            headers=headers,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        parsed = AnalyzeResponse.model_validate(response.json())
        return parsed.decision
