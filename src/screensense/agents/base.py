from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screensense.models import VisionDecision


@dataclass(slots=True)
class ActionStep:
    step_type: Literal[
        "click",
        "type_text",
        "hotkey",
        "wait",
        "clipboard_copy",
        "paste_hotkey",
        "press_enter",
    ]
    target: str = ""
    text: str = ""
    x: int | None = None
    y: int | None = None
    delay_seconds: float = 0.0


@dataclass(slots=True)
class AgentAction:
    description: str
    executable: bool = False
    action_type: Literal[
        "none",
        "clipboard_copy",
        "open_quick_fix",
        "run_command",
        "browser_fill",
        "generic",
        "multi_step",
    ] = "none"
    risk: Literal["low", "medium", "high"] = "medium"
    verification_hint: str | None = None
    steps: list[ActionStep] | None = None


class SubAgent:
    name = "base"

    def plan(self, decision: VisionDecision) -> AgentAction:
        return AgentAction(description=f"{self.name}: no action", executable=False)
