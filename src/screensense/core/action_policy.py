from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screensense.agents.base import AgentAction


@dataclass(slots=True)
class ActionPolicyDecision:
    should_execute: bool
    requires_confirmation: bool
    reason: str


class ActionPolicy:
    _risk_rank = {"low": 0, "medium": 1, "high": 2}

    def __init__(
        self,
        mode: Literal["observe", "ask", "allowlisted_auto"],
        ask_before_act: bool,
        action_allowlist: list[str],
        auto_execute_max_risk: Literal["low", "medium", "high"],
    ) -> None:
        self._mode = mode
        self._ask_before_act = ask_before_act
        self._action_allowlist = set(action_allowlist)
        self._auto_execute_max_risk = auto_execute_max_risk

    def evaluate(self, action: AgentAction) -> ActionPolicyDecision:
        if not action.executable:
            return ActionPolicyDecision(False, False, "non_executable")

        if self._mode == "observe":
            return ActionPolicyDecision(False, False, "observe_mode")

        if self._mode == "ask":
            return ActionPolicyDecision(True, True, "ask_mode")

        allowlisted = action.action_type in self._action_allowlist
        risk_ok = self._risk_rank[action.risk] <= self._risk_rank[self._auto_execute_max_risk]
        if allowlisted and risk_ok and not self._ask_before_act:
            return ActionPolicyDecision(True, False, "allowlisted_auto")

        if self._ask_before_act:
            return ActionPolicyDecision(True, True, "confirmation_required")

        return ActionPolicyDecision(False, False, "not_allowlisted_or_risky")

