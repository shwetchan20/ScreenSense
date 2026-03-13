from screensense.agents.base import ActionStep, AgentAction
import screensense.core.action_executor as action_executor
from screensense.core.action_executor import ActionExecutor


def test_action_executor_preview_contains_core_fields() -> None:
    action = AgentAction(description="Fix import", executable=True, action_type="open_quick_fix", risk="low")
    preview = ActionExecutor.preview(action)
    assert "open_quick_fix" in preview
    assert "low" in preview


def test_action_executor_returns_result_object() -> None:
    action = AgentAction(description="Fix import", executable=True, action_type="clipboard_copy", risk="low")
    executor = ActionExecutor(enabled=True, mode="ask")
    clipboard: dict[str, str] = {"value": ""}

    class _FakeClipboard:
        @staticmethod
        def copy(value: str) -> None:
            clipboard["value"] = value

        @staticmethod
        def paste() -> str:
            return clipboard["value"]

    action_executor.pyperclip = _FakeClipboard()  # type: ignore[assignment]
    result = executor.execute(action)
    assert result.executed
    assert result.verified
    assert result.verification_reason == "clipboard_exact_match"
    assert result.verification_attempts >= 1


def test_action_executor_rejects_unsupported_action_type() -> None:
    action = AgentAction(description="Run risky command", executable=True, action_type="run_command", risk="high")
    executor = ActionExecutor(enabled=True, mode="ask")
    result = executor.execute(action)
    assert not result.executed
    assert "unsupported_action_type" in (result.error or "")
    assert result.verification_reason == "unsupported_action_type"


def test_action_executor_open_quick_fix_reports_unverifiable() -> None:
    pressed: dict[str, str] = {"value": ""}

    class _FakeKeyboard:
        @staticmethod
        def press_and_release(keys: str) -> None:
            pressed["value"] = keys

    action_executor.keyboard = _FakeKeyboard()  # type: ignore[assignment]
    action = AgentAction(description="Open quick fix", executable=True, action_type="open_quick_fix", risk="low")
    executor = ActionExecutor(enabled=True, mode="ask")
    result = executor.execute(action)
    assert result.executed
    assert not result.verified
    assert result.verification_reason == "no_verifier_for_open_quick_fix"
    assert pressed["value"] == "ctrl+."


def test_action_executor_executes_multi_step_plan() -> None:
    pressed: dict[str, list[str]] = {"keys": [], "typed": []}

    class _FakeKeyboard:
        @staticmethod
        def press_and_release(keys: str) -> None:
            pressed["keys"].append(keys)

        @staticmethod
        def write(text: str) -> None:
            pressed["typed"].append(text)

    action_executor.keyboard = _FakeKeyboard()  # type: ignore[assignment]
    action = AgentAction(
        description="Navigate and search",
        executable=True,
        action_type="multi_step",
        risk="low",
        steps=[
            ActionStep(step_type="hotkey", target="ctrl+l"),
            ActionStep(step_type="type_text", text="screensense"),
            ActionStep(step_type="press_enter"),
        ],
    )
    executor = ActionExecutor(enabled=True, mode="ask")
    result = executor.execute(action)
    assert result.executed
    assert result.verified
    assert result.verification_reason == "plan_executed_no_hint"
    assert [s.success for s in (result.step_results or [])] == [True, True, True]
    assert pressed["keys"] == ["ctrl+l", "enter"]
    assert pressed["typed"] == ["screensense"]
