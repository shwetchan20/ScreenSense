from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class VisionDecision(BaseModel):
    context: str = Field(default="Unknown")
    should_interrupt: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    message: str = ""
    can_fix: bool = False
    priority: Literal["critical", "helpful", "silent"] = "helpful"
    domain: Literal["code", "translate", "browse", "general"] = "general"
    proposed_action: str | None = None


@dataclass(slots=True)
class ScreenObservation:
    changed_percent: float
    decision: VisionDecision
