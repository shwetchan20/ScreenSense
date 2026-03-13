from screensense.agents.router import AgentRouter
from screensense.models import VisionDecision
from screensense.orchestration.adk_runner import AgentRunner
import importlib.util
import pytest


def _decision() -> VisionDecision:
    return VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.9,
        message="Type error spotted",
        can_fix=True,
        priority="helpful",
        domain="code",
        proposed_action="Patch argument type",
    )


def test_runner_uses_local_when_forced() -> None:
    runner = AgentRunner(router=AgentRouter(), runtime_mode="local")
    result = runner.run("code", _decision())
    assert result.backend == "local"
    assert result.action.executable


def test_runner_falls_back_to_local_when_adk_unavailable() -> None:
    runner = AgentRunner(router=AgentRouter(), runtime_mode="adk")
    result = runner.run("general", _decision())
    assert result.backend in {"local", "google_adk"}
    assert result.action.description


def test_runner_strict_mode_raises_when_adk_unavailable() -> None:
    # Strict mode should raise only when ADK is truly unavailable.
    if importlib.util.find_spec("google.adk") is not None:
        pytest.skip("google.adk is available in this environment")
    with pytest.raises(RuntimeError):
        AgentRunner(router=AgentRouter(), runtime_mode="adk", strict=True)
