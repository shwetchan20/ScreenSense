from __future__ import annotations

import json
from io import BytesIO
import time

import numpy as np
from google import genai
from PIL import Image
from pydantic import ValidationError

from screensense.models import VisionDecision


PROMPT = """You are ARIA, a sharp proactive desktop co-pilot watching the user's screen.
Analyze this screenshot and return ONLY compact JSON:
{
  "context": "short app/task label",
  "should_interrupt": true|false,
  "confidence": 0.0-1.0,
  "message": "helpful one-liner",
  "can_fix": true|false,
  "priority": "critical|helpful|silent",
  "domain": "code|translate|browse|general",
  "proposed_action": "optional explicit action"
}
Rules:
- You can SEE the actual screen. Always reference something specific that is visible.
- Speak in maximum 24 words, up to 2 short sentences.
- Sound like a smart observant colleague, not a help desk assistant.
- Avoid filler like "I noticed", "it seems", "you might want to", "consider", "remember to".
- NEVER be generic. "GEMINI_API_KEY is empty" is good. "Check your env vars" is not.
- NEVER repeat a suggestion made recently.
- If there is nothing genuinely useful and specific to say, set confidence to 0.0 and message to empty.
- Use ui_text_excerpt and app metadata for exact grounding.
- No markdown, no extra keys.
"""


class GeminiVisionClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._last_ts = 0.0
        self._last_context_hash = ""
        self._last_decision: VisionDecision | None = None

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        if app_context and app_context.get("gemini_allowed") is False:
            return VisionDecision(
                context="GeminiSkipped",
                should_interrupt=False,
                confidence=0.0,
                message="",
                can_fix=False,
                domain="general",
            )
        context_text = self._format_context(app_context)
        context_hash = str(hash(context_text))
        now = time.time()
        if (now - self._last_ts) < 60:
            if self._last_decision is not None:
                return self._last_decision
            return VisionDecision(
                context="GeminiRateLimited",
                should_interrupt=False,
                confidence=0.0,
                message="",
                can_fix=False,
                domain="general",
            )
        if self._last_decision is not None and context_hash == self._last_context_hash and (
            now - self._last_ts
        ) < 30:
            return self._last_decision
        image = Image.fromarray(frame_rgb)
        buf = BytesIO()
        image.save(buf, format="PNG")
        raw = self._client.models.generate_content(
            model=self._model,
            contents=[
                {"text": f"{PROMPT}\n\n{context_text}"},
                {"inline_data": {"mime_type": "image/png", "data": buf.getvalue()}},
            ],
        )
        text = (raw.text or "").strip()
        data = self._extract_json(text)
        try:
            decision = VisionDecision.model_validate(data)
        except ValidationError:
            decision = VisionDecision(
                context="ParseError",
                should_interrupt=False,
                confidence=0.0,
                message="Model response failed schema validation.",
                can_fix=False,
                domain="general",
            )
        self._last_ts = now
        self._last_context_hash = context_hash
        self._last_decision = decision
        return decision

    @staticmethod
    def _extract_json(text: str) -> dict:
        if not text:
            return {}
        if text.startswith("{") and text.endswith("}"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {}
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _format_context(app_context: dict[str, str | int | bool | None] | None) -> str:
        if not app_context:
            return "Active app context: unavailable"
        ordered_keys = [
            "window_title",
            "process_name",
            "executable_name",
            "pid",
            "assistant_name",
            "assistant_persona",
            "user_name",
            "project_name",
            "now_iso",
            "weekday",
            "time_block",
            "session_minutes",
            "away",
            "goal",
            "deadline_days_left",
            "memory_digest",
            "ui_ocr_enabled",
            "ui_ocr_provider",
            "ui_text_excerpt",
            "ui_text_cached",
        ]
        lines = ["Active app context:"]
        seen: set[str] = set()
        for key in ordered_keys:
            if key in app_context:
                seen.add(key)
                lines.append(f"- {key}: {app_context.get(key)}")
        for key in sorted(app_context.keys()):
            if key in seen:
                continue
            lines.append(f"- {key}: {app_context.get(key)}")
        return "\n".join(lines)
