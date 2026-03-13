from __future__ import annotations

import time

from screensense.models import VisionDecision


class GoalEngine:
    def __init__(self) -> None:
        self._current_goal = "Reduce friction and ship stable progress"
        self._last_update_ts = 0.0

    def update(self, decision: VisionDecision, *, active_window_title: str) -> str:
        text = " ".join(
            [
                decision.context or "",
                decision.domain or "",
                decision.message or "",
                active_window_title or "",
            ]
        ).lower()

        if any(token in text for token in ("vscode", "pycharm", "pytest", "traceback", "exception")):
            goal = "Ship stable code and clear active bugs"
        elif any(token in text for token in ("browser", "form", "website", "tab", "chrome", "edge")):
            goal = "Complete the current web workflow with minimal context switching"
        elif any(token in text for token in ("translate", "language", "subtitle")):
            goal = "Translate content accurately without losing intent"
        else:
            goal = "Maintain momentum and remove the next blocker quickly"

        if goal != self._current_goal:
            self._current_goal = goal
            self._last_update_ts = time.time()
        return self._current_goal

    def summary(self) -> str:
        return self._current_goal
