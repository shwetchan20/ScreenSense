from screensense.agents.base import AgentAction
from screensense.core.action_policy import ActionPolicy


def test_observe_mode_skips_execution() -> None:
    policy = ActionPolicy("observe", ask_before_act=True, action_allowlist=["open_quick_fix"], auto_execute_max_risk="low")
    action = AgentAction(description="x", executable=True, action_type="open_quick_fix", risk="low")
    decision = policy.evaluate(action)
    assert not decision.should_execute
    assert decision.reason == "observe_mode"


def test_ask_mode_requires_confirmation() -> None:
    policy = ActionPolicy("ask", ask_before_act=True, action_allowlist=["open_quick_fix"], auto_execute_max_risk="low")
    action = AgentAction(description="x", executable=True, action_type="open_quick_fix", risk="low")
    decision = policy.evaluate(action)
    assert decision.should_execute
    assert decision.requires_confirmation
    assert decision.reason == "ask_mode"


def test_allowlisted_auto_runs_without_confirmation_when_safe() -> None:
    policy = ActionPolicy(
        "allowlisted_auto",
        ask_before_act=False,
        action_allowlist=["open_quick_fix"],
        auto_execute_max_risk="medium",
    )
    action = AgentAction(description="x", executable=True, action_type="open_quick_fix", risk="medium")
    decision = policy.evaluate(action)
    assert decision.should_execute
    assert not decision.requires_confirmation
    assert decision.reason == "allowlisted_auto"

