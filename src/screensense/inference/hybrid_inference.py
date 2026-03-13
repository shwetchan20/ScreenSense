from __future__ import annotations

import re

import numpy as np

from screensense.inference.base import InferenceClient
from screensense.models import VisionDecision


class HybridInferenceClient:
    def __init__(
        self,
        *,
        local_client: InferenceClient,
        gemini_client: InferenceClient,
        escalate_confidence_threshold: float = 0.72,
        force_gemini_on_critical: bool = True,
    ) -> None:
        self._local = local_client
        self._gemini = gemini_client
        self._threshold = max(0.0, min(1.0, escalate_confidence_threshold))
        self._force_gemini_on_critical = force_gemini_on_critical
        self.last_source = "local"
        self.last_escalation_reason = ""

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        local = self._local.analyze(frame_rgb=frame_rgb, app_context=app_context)
        if app_context and app_context.get("gemini_allowed") is False:
            self.last_source = "local"
            self.last_escalation_reason = ""
            return local
        reason = self._escalation_reason(local)
        if reason is None:
            self.last_source = "local"
            self.last_escalation_reason = ""
            return local

        context = dict(app_context or {})
        context["hybrid_local_context"] = local.context
        context["hybrid_local_confidence"] = local.confidence
        context["hybrid_local_message"] = local.message
        self.last_source = "gemini"
        self.last_escalation_reason = reason
        return self._gemini.analyze(frame_rgb=frame_rgb, app_context=context)

    def _escalation_reason(self, decision: VisionDecision) -> str | None:
        if decision.confidence < self._threshold:
            return "low_confidence"
        if self._force_gemini_on_critical and decision.priority == "critical":
            return "critical_policy"
        normalized_context = decision.context.strip().lower()
        if normalized_context in {"unknown", "parseerror", "desktop"}:
            return "weak_context"
        return None
