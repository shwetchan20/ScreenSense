from __future__ import annotations

import json
import re
from collections import deque
from typing import Any

import numpy as np
import requests
from pydantic import ValidationError

from screensense.core.ui_context import UiContextExtractor
from screensense.inference.image_codec import encode_png_base64
from screensense.models import VisionDecision


LOCAL_PROMPT = """You are ARIA, a laptop AI.
Study these examples. Output must be ONLY compact JSON.

Example 1
Screen: VS Code, auth.py (screensense), terminal: pytest failed: ImportError...
Goal: fix ui_context
Output:
{"context":"VS Code auth.py","should_interrupt":true,"confidence":0.86,"message":"auth.py is open and pytest is failing (ImportError).","can_fix":true,"priority":"helpful","domain":"code","proposed_action":"open_quick_fix"}

Example 2
Screen: Chrome (screensense), ERRORS:
Goal: none
Output:
{"context":"Chrome","should_interrupt":false,"confidence":0.55,"message":"Chrome is active; no concrete error signal yet.","can_fix":false,"priority":"silent","domain":"general"}

Example 3
Screen: WindowsTerminal, terminal: error: connection refused 127.0.0.1:11434
Goal: get qwen online
Output:
{"context":"Terminal","should_interrupt":true,"confidence":0.84,"message":"Ollama looks down (connection refused); restart it before relying on local Qwen.","can_fix":false,"priority":"critical","domain":"general"}

Now respond exactly like the examples:
- Short. Observational. No greetings. No questions.
- Prefer silence when weak: if unsure, set should_interrupt=false and priority=silent.
- Use ONLY real clues from Screen/context; don't invent filenames or errors.
- Output JSON only (no markdown, no extra text).

FACTS:
User: Shwet
Project: ScreenSense
Deadline: {deadline_date} ({days_remaining} days)
Time: {time}
Goal: {session_goal}
Screen: {active_app}
Context: {ui_context}
Recent history: {memory_recent_5}
Last rejection: {last_rejection}
"""


class LocalQwenInferenceClient:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        use_vision: bool = True,
        ui_context_extractor: UiContextExtractor | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._use_vision = use_vision
        self._ui_context_extractor = ui_context_extractor
        self.last_source = "local_qwen"
        self._recent_messages: deque[str] = deque(maxlen=8)

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        context = dict(app_context or {})
        if self._ui_context_extractor is not None:
            context = self._ui_context_extractor.enrich(frame_rgb=frame_rgb, app_context=context)

        if self._provider != "ollama":
            return self._fallback_decision(context, reason="local_llm_provider_disabled")

        filled_prompt = LOCAL_PROMPT.format(
            deadline_date=context.get("deadline_date", "unknown"),
            days_remaining=context.get("deadline_days_left", "?"),
            time=str(context.get("now_iso", ""))[:16],
            session_start=context.get("session_start", "unknown"),
            session_goal=context.get("goal", context.get("session_goal", "none")),
            active_app=context.get("window_title", context.get("process_name", "unknown")),
            ui_context=context.get("ui_text", json.dumps(context.get("ui_context", {}), ensure_ascii=True)),
            memory_recent_5=context.get("memory_digest", "none"),
            last_rejection=context.get("last_rejection", "none"),
        )
        payload = {
            "model": self._model,
            "prompt": f"{filled_prompt}\n\nContext:\n{json.dumps(context, ensure_ascii=True)}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        if self._should_send_vision_frame():
            payload["images"] = [encode_png_base64(frame_rgb[::2, ::2])]
        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            text = str(body.get("response") or "").strip()
            data = self._extract_json(text)
            decision = VisionDecision.model_validate(data)
            if not decision.context.strip():
                return self._fallback_decision(context, reason="local_blank_context")
            decision = self._normalize_decision(decision, context)
            if decision.message.strip():
                self._recent_messages.append(decision.message.strip().lower())
            return decision
        except (requests.RequestException, ValidationError, ValueError, json.JSONDecodeError):
            return self._fallback_decision(context, reason="local_llm_error")

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        return {}

    @staticmethod
    def _fallback_decision(
        context: dict[str, str | int | bool | None],
        *,
        reason: str,
    ) -> VisionDecision:
        title = str(context.get("window_title") or "Desktop")
        title = re.sub(r"\s+", " ", title).strip()
        return VisionDecision(
            context=title[:50] or "Desktop",
            should_interrupt=False,
            confidence=0.25,
            message=f"Local reasoning unavailable ({reason}). Monitoring silently.",
            can_fix=False,
            priority="silent",
            domain="general",
        )

    def _normalize_decision(
        self,
        decision: VisionDecision,
        context: dict[str, str | int | bool | None],
    ) -> VisionDecision:
        message = re.sub(r"\s+", " ", decision.message.strip())
        message = _limit_sentences(message, max_sentences=2)
        lowered = message.lower()
        generic_patterns = (
            "stay focused",
            "keep coding",
            "more coding left",
            "more videos await",
            "great content ahead",
        )
        if not message or any(p in lowered for p in generic_patterns):
            app = str(context.get("window_title") or context.get("process_name") or "screen").strip()
            excerpt = str(context.get("ui_text_excerpt") or "").strip()
            clue = self._best_clue(excerpt)
            message = f"{app}: {clue}" if clue else f"{app}: notable screen change detected."

        # De-repeat if exact line was just used.
        if message.lower() in self._recent_messages:
            app = str(context.get("window_title") or "screen").strip()
            message = f"{message} Check {app} now."

        if len(message) > 180:
            message = message[:177].rstrip() + "..."
        decision.message = message
        return decision

    def _should_send_vision_frame(self) -> bool:
        if not self._use_vision:
            return False
        model = self._model.lower()
        return any(tag in model for tag in ("vl", "vision", "llava", "minicpm"))

    @staticmethod
    def _best_clue(excerpt: str) -> str:
        cleaned = re.sub(r"\s+", " ", excerpt).strip()
        if not cleaned:
            return ""
        keywords = (
            "error",
            "exception",
            "traceback",
            "failed",
            "failure",
            "warning",
            "warn",
            "todo",
            "fixme",
            "line ",
            "undefined",
            "null",
            "stack",
            "denied",
            "forbidden",
            "timeout",
        )
        lowered = cleaned.lower()
        for key in keywords:
            idx = lowered.find(key)
            if idx >= 0:
                start = max(0, idx - 18)
                end = min(len(cleaned), idx + 62)
                return cleaned[start:end].strip()
        return cleaned[:96]


def _limit_sentences(text: str, *, max_sentences: int) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    limited = " ".join(parts[:max_sentences]).strip()
    return limited
