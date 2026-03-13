from __future__ import annotations

from screensense.agents.base import AgentAction, SubAgent
from screensense.models import VisionDecision


class TranslateAgent(SubAgent):
    name = "translate"

    def plan(self, decision: VisionDecision) -> AgentAction:
        if decision.proposed_action:
            return AgentAction(description=decision.proposed_action, executable=False)
        return AgentAction(description="Translation hint available.", executable=False)

