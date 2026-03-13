from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screensense.agents.base import AgentAction, SubAgent
from screensense.agents.router import AgentRouter
from screensense.models import VisionDecision


@dataclass(slots=True)
class RunnerExecutionResult:
    action: AgentAction
    backend: Literal["google_adk", "local"]
    runtime_note: str


class DomainAgent:
    def __init__(self, name: str, sub_agent: SubAgent) -> None:
        self.name = name
        self._sub_agent = sub_agent

    def run(self, decision: VisionDecision) -> AgentAction:
        return self._sub_agent.plan(decision)


class AgentRunner:
    """Runner abstraction that prefers Google ADK and gracefully falls back."""

    def __init__(
        self,
        router: AgentRouter,
        runtime_mode: Literal["adk", "local"],
        strict: bool = False,
    ) -> None:
        self._agents: dict[str, DomainAgent] = {
            "code": DomainAgent("code", router.get("code")),
            "translate": DomainAgent("translate", router.get("translate")),
            "browse": DomainAgent("browse", router.get("browse")),
            "general": DomainAgent("general", router.get("general")),
        }
        self._runtime_mode = runtime_mode
        self._strict = strict
        self._backend: Literal["google_adk", "local"] = "local"
        self._runtime_note = "local runner active"
        self._adk_runner = None
        self._adk_session_service = None
        if runtime_mode == "adk":
            self._try_init_google_adk()
            if self._strict and self._backend != "google_adk":
                raise RuntimeError(
                    f"AGENT_RUNTIME_MODE=adk requires Google ADK. {self._runtime_note}"
                )

    @property
    def backend(self) -> Literal["google_adk", "local"]:
        return self._backend

    @property
    def runtime_note(self) -> str:
        return self._runtime_note

    def run(self, domain: str, decision: VisionDecision) -> RunnerExecutionResult:
        agent = self._agents.get(domain, self._agents["general"])
        action = agent.run(decision)
        return RunnerExecutionResult(
            action=action,
            backend=self._backend,
            runtime_note=self._runtime_note,
        )

    def _try_init_google_adk(self) -> None:
        try:
            from google.adk.runners import Runner as GoogleADKRunner  # type: ignore
            from google.adk.sessions import InMemorySessionService  # type: ignore
            from google.adk.agents import Agent as GoogleADKAgent  # type: ignore
        except Exception:
            self._backend = "local"
            self._runtime_note = "google adk package unavailable; using local runner"
            return

        try:
            self._adk_session_service = InMemorySessionService()
            adk_agent = GoogleADKAgent(
                name="screensense_root",
                description="ScreenSense root coordinator agent.",
            )
            self._adk_runner = GoogleADKRunner(
                app_name="screensense",
                agent=adk_agent,
                session_service=self._adk_session_service,
            )
            self._backend = "google_adk"
            self._runtime_note = "google adk initialized; domain routing in hybrid mode"
        except Exception as exc:
            self._backend = "local"
            self._runtime_note = f"google adk init failed ({type(exc).__name__}); using local runner"
