from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Literal

try:
    import keyboard
except Exception:  # pragma: no cover
    keyboard = None  # type: ignore[assignment]

try:
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None  # type: ignore[assignment]

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None  # type: ignore[assignment]

from screensense.agents.base import ActionStep, AgentAction


@dataclass(slots=True)
class StepExecutionResult:
    index: int
    step_type: str
    success: bool
    error: str | None = None


@dataclass(slots=True)
class ActionExecutionResult:
    executed: bool
    verified: bool
    error: str | None = None
    verification_reason: str = "not_checked"
    verification_attempts: int = 0
    step_results: list[StepExecutionResult] | None = None


class ActionExecutor:
    def __init__(
        self,
        enabled: bool,
        mode: Literal["observe", "ask", "allowlisted_auto"],
    ) -> None:
        self._enabled = enabled
        self._mode = mode

    @staticmethod
    def preview(action: AgentAction) -> str:
        return (
            f"type={action.action_type}, risk={action.risk}, "
            f"detail={action.description}"
        )

    def execute(self, action: AgentAction) -> ActionExecutionResult:
        if not self._enabled or not action.executable:
            return ActionExecutionResult(
                executed=False,
                verified=False,
                error="disabled_or_non_executable",
                verification_reason="not_executed",
            )
        if self._mode == "observe":
            return ActionExecutionResult(
                executed=False,
                verified=False,
                error="observe_mode",
                verification_reason="not_executed",
            )
        try:
            if action.steps:
                return self._execute_plan(action)
            if action.action_type == "clipboard_copy":
                if pyperclip is None:
                    return ActionExecutionResult(
                        executed=False,
                        verified=False,
                        error="pyperclip_not_available",
                        verification_reason="executor_dependency_missing",
                    )
                pyperclip.copy(action.description)
            elif action.action_type == "open_quick_fix":
                if keyboard is None:
                    return ActionExecutionResult(
                        executed=False,
                        verified=False,
                        error="keyboard_not_available",
                        verification_reason="executor_dependency_missing",
                    )
                keyboard.press_and_release("ctrl+.")
            else:
                return ActionExecutionResult(
                    executed=False,
                    verified=False,
                    error=f"unsupported_action_type:{action.action_type}",
                    verification_reason="unsupported_action_type",
                )
        except Exception as exc:
            return ActionExecutionResult(
                executed=False,
                verified=False,
                error=str(exc),
                verification_reason="execution_exception",
            )

        verified, reason, attempts = self._verify_with_retries(action, max_attempts=3, retry_delay_seconds=0.15)
        return ActionExecutionResult(
            executed=True,
            verified=verified,
            verification_reason=reason,
            verification_attempts=attempts,
        )

    def _execute_plan(self, action: AgentAction) -> ActionExecutionResult:
        step_results: list[StepExecutionResult] = []
        for idx, step in enumerate(action.steps or [], start=1):
            ok, err = self._execute_step(step)
            step_results.append(
                StepExecutionResult(index=idx, step_type=step.step_type, success=ok, error=err)
            )
            if not ok:
                return ActionExecutionResult(
                    executed=False,
                    verified=False,
                    error=f"step_failed:{idx}:{step.step_type}:{err or 'unknown'}",
                    verification_reason="plan_execution_failed",
                    verification_attempts=0,
                    step_results=step_results,
                )
        verified, reason, attempts = self._verify_with_retries(action, max_attempts=3, retry_delay_seconds=0.15)
        return ActionExecutionResult(
            executed=True,
            verified=verified,
            verification_reason=reason,
            verification_attempts=attempts,
            step_results=step_results,
        )

    @staticmethod
    def _execute_step(step: ActionStep) -> tuple[bool, str | None]:
        try:
            if step.step_type == "wait":
                time.sleep(max(0.0, step.delay_seconds))
                return True, None
            if step.step_type == "clipboard_copy":
                if pyperclip is None:
                    return False, "pyperclip_not_available"
                pyperclip.copy(step.text)
                return True, None
            if step.step_type == "type_text":
                if keyboard is None:
                    return False, "keyboard_not_available"
                keyboard.write(step.text)
                return True, None
            if step.step_type == "hotkey":
                if keyboard is None:
                    return False, "keyboard_not_available"
                keyboard.press_and_release(step.target)
                return True, None
            if step.step_type == "paste_hotkey":
                if keyboard is None:
                    return False, "keyboard_not_available"
                keyboard.press_and_release("ctrl+v")
                return True, None
            if step.step_type == "press_enter":
                if keyboard is None:
                    return False, "keyboard_not_available"
                keyboard.press_and_release("enter")
                return True, None
            if step.step_type == "click":
                if pyautogui is None:
                    return False, "pyautogui_not_available"
                if step.x is None or step.y is None:
                    return False, "missing_coordinates"
                pyautogui.click(step.x, step.y)
                return True, None
            return False, f"unsupported_step_type:{step.step_type}"
        except Exception as exc:  # pragma: no cover
            return False, str(exc)

    @staticmethod
    def _verify_with_retries(
        action: AgentAction,
        *,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> tuple[bool, str, int]:
        for attempt in range(1, max_attempts + 1):
            verified, reason = ActionExecutor._verify_once(action)
            if verified:
                return True, reason, attempt
            if attempt < max_attempts:
                time.sleep(retry_delay_seconds)
        return False, reason, max_attempts

    @staticmethod
    def _verify_once(action: AgentAction) -> tuple[bool, str]:
        if action.steps:
            if action.verification_hint:
                return ActionExecutor._verify_hint(action.verification_hint, action)
            return True, "plan_executed_no_hint"
        if action.action_type == "clipboard_copy":
            try:
                if pyperclip is None:
                    return False, "pyperclip_not_available"
                pasted = pyperclip.paste()
                if action.verification_hint and action.verification_hint.startswith("clipboard_contains:"):
                    expected = action.verification_hint.split(":", 1)[1]
                    if expected and expected in pasted:
                        return True, "clipboard_contains_match"
                    return False, "clipboard_contains_mismatch"
                if pasted == action.description:
                    return True, "clipboard_exact_match"
                return False, "clipboard_exact_mismatch"
            except Exception:
                return False, "clipboard_read_exception"
        if action.action_type == "open_quick_fix":
            return False, "no_verifier_for_open_quick_fix"
        return False, "no_verifier_for_action_type"

    @staticmethod
    def _verify_hint(verification_hint: str, action: AgentAction) -> tuple[bool, str]:
        hint = verification_hint.strip()
        if hint.startswith("clipboard_contains:"):
            expected = hint.split(":", 1)[1]
            if pyperclip is None:
                return False, "pyperclip_not_available"
            try:
                pasted = pyperclip.paste()
            except Exception:
                return False, "clipboard_read_exception"
            if expected in pasted:
                return True, "clipboard_contains_match"
            return False, "clipboard_contains_mismatch"
        if hint.lower().startswith("verify target form field"):
            return True, "manual_verification_hint"
        if action.action_type == "open_quick_fix":
            return False, "no_verifier_for_open_quick_fix"
        return True, "unrecognized_hint_assumed_true"
