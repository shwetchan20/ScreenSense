from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from screensense.models import VisionDecision


@dataclass(slots=True)
class PersonaProfile:
    proactive_bias: float = 0.5
    brevity_bias: float = 0.6
    humor_bias: float = 0.25
    directness_bias: float = 0.6
    trust_score: float = 0.5


class PersonaAdapter:
    def __init__(
        self,
        *,
        enabled: bool,
        path: str,
        assistant_name: str,
        user_name: str,
        base_persona: str,
    ) -> None:
        self._enabled = enabled
        self._path = Path(path)
        self._assistant_name = assistant_name.strip() or "ARIA"
        self._user_name = user_name.strip() or "Operator"
        self._base_persona = base_persona.strip() or "calm concise proactive with dry wit"
        self._profile = self._load_or_default()

    @property
    def profile(self) -> PersonaProfile:
        return self._profile

    def compose_message(self, *, decision: VisionDecision, goal: str, base_message: str) -> str:
        if not self._enabled:
            return base_message
        text = decision.message.strip() or base_message.strip()
        if not text:
            return ""
        if self._profile.directness_bias >= 0.65:
            msg = f"{self._user_name}, {text} Goal: {goal}."
        else:
            msg = f"{self._user_name}, quick update: {text} We can keep moving on {goal}."
        if self._profile.proactive_bias >= 0.65 and decision.can_fix:
            msg = f"{msg} Say yes and I'll handle the next step."
        if self._profile.humor_bias >= 0.55:
            msg = f"{msg} Clean and surgical, no chaos."
        if self._profile.brevity_bias >= 0.7 and len(msg) > 150:
            msg = msg[:147].rstrip() + "..."
        return msg

    def record_feedback(self, *, event: str, reason: str = "") -> None:
        if not self._enabled:
            return
        if event == "action_executed":
            self._profile.trust_score = self._clamp(self._profile.trust_score + 0.03)
            self._profile.proactive_bias = self._clamp(self._profile.proactive_bias + 0.02)
            self._profile.directness_bias = self._clamp(self._profile.directness_bias + 0.01)
        elif event == "action_denied":
            self._profile.trust_score = self._clamp(self._profile.trust_score - 0.05)
            self._profile.proactive_bias = self._clamp(self._profile.proactive_bias - 0.05)
            self._profile.brevity_bias = self._clamp(self._profile.brevity_bias + 0.02)
        elif event == "action_skipped" and reason == "non_executable":
            self._profile.directness_bias = self._clamp(self._profile.directness_bias + 0.02)
            self._profile.brevity_bias = self._clamp(self._profile.brevity_bias + 0.01)
        self._save()

    def _load_or_default(self) -> PersonaProfile:
        if not self._enabled:
            return PersonaProfile()
        if not self._path.exists():
            return PersonaProfile()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return PersonaProfile(
                proactive_bias=float(payload.get("proactive_bias", 0.5)),
                brevity_bias=float(payload.get("brevity_bias", 0.6)),
                humor_bias=float(payload.get("humor_bias", 0.25)),
                directness_bias=float(payload.get("directness_bias", 0.6)),
                trust_score=float(payload.get("trust_score", 0.5)),
            )
        except Exception:
            return PersonaProfile()

    def _save(self) -> None:
        if not self._enabled:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "assistant_name": self._assistant_name,
            "base_persona": self._base_persona,
            "proactive_bias": round(self._profile.proactive_bias, 4),
            "brevity_bias": round(self._profile.brevity_bias, 4),
            "humor_bias": round(self._profile.humor_bias, 4),
            "directness_bias": round(self._profile.directness_bias, 4),
            "trust_score": round(self._profile.trust_score, 4),
        }
        self._path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
