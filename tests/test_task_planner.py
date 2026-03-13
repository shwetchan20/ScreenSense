from screensense.agents.base import ActionStep, AgentAction
from screensense.core.task_planner import TaskPlanner
from screensense.models import VisionDecision


def _decision() -> VisionDecision:
    return VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.9,
        message="Type error in tests.",
        can_fix=True,
        priority="helpful",
        domain="code",
    )


def test_task_planner_builds_plan_from_explicit_steps() -> None:
    planner = TaskPlanner()
    action = AgentAction(
        description="Do browser search",
        executable=True,
        action_type="multi_step",
        risk="low",
        steps=[
            ActionStep(step_type="hotkey", target="ctrl+l"),
            ActionStep(step_type="type_text", text="screensense"),
            ActionStep(step_type="press_enter"),
        ],
    )
    plan = planner.build(decision=_decision(), action=action, goal="Ship stable code")
    assert plan.plan_id
    assert len(plan.steps) == 3
    assert plan.steps[0].step_type == "hotkey"
    assert "Hotkey" in plan.steps[0].success_criteria


def test_task_planner_builds_legacy_fallback_step() -> None:
    planner = TaskPlanner()
    action = AgentAction(
        description="Copy patch",
        executable=True,
        action_type="clipboard_copy",
        risk="low",
    )
    plan = planner.build(decision=_decision(), action=action, goal="Fix bug")
    assert len(plan.steps) == 1
    assert plan.steps[0].step_type == "clipboard_copy"
