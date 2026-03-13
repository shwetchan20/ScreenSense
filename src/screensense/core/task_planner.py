from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1

from screensense.agents.base import ActionStep, AgentAction
from screensense.models import VisionDecision


@dataclass(slots=True)
class PlanStep:
    index: int
    label: str
    step_type: str
    success_criteria: str
    step: ActionStep


@dataclass(slots=True)
class TaskPlan:
    plan_id: str
    goal: str
    domain: str
    created_ts: str
    steps: list[PlanStep]


class TaskPlanner:
    def build(
        self,
        *,
        decision: VisionDecision,
        action: AgentAction,
        goal: str,
    ) -> TaskPlan:
        created_ts = datetime.now(timezone.utc).isoformat()
        seed = f"{decision.domain}|{goal}|{action.description}|{created_ts}"
        plan_id = sha1(seed.encode("utf-8")).hexdigest()[:12]
        steps = self._steps_for_action(action)
        return TaskPlan(
            plan_id=plan_id,
            goal=goal,
            domain=decision.domain,
            created_ts=created_ts,
            steps=steps,
        )

    def _steps_for_action(self, action: AgentAction) -> list[PlanStep]:
        if action.steps:
            out: list[PlanStep] = []
            for idx, step in enumerate(action.steps, start=1):
                out.append(
                    PlanStep(
                        index=idx,
                        label=f"step_{idx}_{step.step_type}",
                        step_type=step.step_type,
                        success_criteria=self._criteria_for_step(step),
                        step=step,
                    )
                )
            return out

        default_step = self._legacy_to_step(action)
        return [
            PlanStep(
                index=1,
                label=f"step_1_{default_step.step_type}",
                step_type=default_step.step_type,
                success_criteria=self._criteria_for_step(default_step),
                step=default_step,
            )
        ]

    @staticmethod
    def _legacy_to_step(action: AgentAction) -> ActionStep:
        if action.action_type == "clipboard_copy":
            return ActionStep(step_type="clipboard_copy", text=action.description)
        if action.action_type == "open_quick_fix":
            return ActionStep(step_type="hotkey", target="ctrl+.")
        if action.action_type == "browser_fill":
            return ActionStep(step_type="type_text", text=action.description)
        return ActionStep(step_type="wait", delay_seconds=0.0)

    @staticmethod
    def _criteria_for_step(step: ActionStep) -> str:
        if step.step_type == "clipboard_copy":
            return "Clipboard content updated"
        if step.step_type == "click":
            return "Pointer interaction executed at target location"
        if step.step_type == "type_text":
            return "Text injected into focused target"
        if step.step_type == "hotkey":
            return "Hotkey dispatched to active window"
        if step.step_type == "press_enter":
            return "Enter key submitted current interaction"
        if step.step_type == "paste_hotkey":
            return "Clipboard pasted in focused target"
        if step.step_type == "wait":
            return "Delay elapsed for asynchronous UI stabilization"
        return "Step executed"
