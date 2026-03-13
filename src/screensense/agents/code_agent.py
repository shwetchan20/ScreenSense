from __future__ import annotations

from screensense.agents.base import AgentAction, SubAgent
from screensense.models import VisionDecision


class CodeAgent(SubAgent):
    name = "code"

    def plan(self, decision: VisionDecision) -> AgentAction:
        if decision.can_fix and decision.proposed_action:
            return AgentAction(
                description=f"Suggested fix:\n{decision.proposed_action}",
                executable=True,
                action_type="clipboard_copy",
                risk="low",
                verification_hint="Verify clipboard content is updated with the suggested fix.",
            )
        return AgentAction(
            description="Code issue detected. Suggest manual review.",
            executable=False,
        )
