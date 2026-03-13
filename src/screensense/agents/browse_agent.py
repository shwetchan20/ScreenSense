from __future__ import annotations

from screensense.agents.base import ActionStep, AgentAction, SubAgent
from screensense.models import VisionDecision


class BrowseAgent(SubAgent):
    name = "browse"

    def plan(self, decision: VisionDecision) -> AgentAction:
        if decision.can_fix and decision.proposed_action:
            return AgentAction(
                description=decision.proposed_action,
                executable=True,
                action_type="multi_step",
                risk="medium",
                verification_hint="Verify target form field or page state changed.",
                steps=[
                    ActionStep(step_type="hotkey", target="ctrl+l"),
                    ActionStep(step_type="wait", delay_seconds=0.1),
                    ActionStep(step_type="type_text", text=decision.proposed_action),
                    ActionStep(step_type="press_enter"),
                ],
            )
        return AgentAction(description="Browser task recognized.", executable=False)
