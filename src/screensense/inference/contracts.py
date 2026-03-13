from __future__ import annotations

from pydantic import BaseModel, Field

from screensense.models import VisionDecision


class AnalyzeRequest(BaseModel):
    screenshot_png_base64: str = Field(min_length=1)
    app_context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    decision: VisionDecision
