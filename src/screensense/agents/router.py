from __future__ import annotations

from screensense.agents.base import SubAgent
from screensense.agents.browse_agent import BrowseAgent
from screensense.agents.code_agent import CodeAgent
from screensense.agents.general_agent import GeneralAgent
from screensense.agents.translate_agent import TranslateAgent


class AgentRouter:
    def __init__(self) -> None:
        self._agents: dict[str, SubAgent] = {
            "code": CodeAgent(),
            "translate": TranslateAgent(),
            "browse": BrowseAgent(),
            "general": GeneralAgent(),
        }

    def get(self, domain: str) -> SubAgent:
        return self._agents.get(domain, self._agents["general"])

