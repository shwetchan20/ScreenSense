import numpy as np

from screensense.inference.hybrid_inference import HybridInferenceClient
from screensense.models import VisionDecision


class _StubClient:
    def __init__(self, decision: VisionDecision) -> None:
        self._decision = decision
        self.calls = 0

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        _ = (frame_rgb, app_context)
        self.calls += 1
        return self._decision


def _local_decision(confidence: float, *, priority: str = "helpful") -> VisionDecision:
    return VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=confidence,
        message="Type error found in test execution.",
        can_fix=True,
        priority=priority,  # type: ignore[arg-type]
        domain="code",
    )


def test_hybrid_uses_local_when_confident() -> None:
    local = _StubClient(_local_decision(0.9))
    gemini = _StubClient(_local_decision(0.99, priority="critical"))
    client = HybridInferenceClient(
        local_client=local,
        gemini_client=gemini,
        escalate_confidence_threshold=0.72,
        force_gemini_on_critical=False,
    )
    out = client.analyze(np.zeros((5, 5, 3), dtype="uint8"), app_context={})
    assert out.confidence == 0.9
    assert client.last_source == "local"
    assert local.calls == 1
    assert gemini.calls == 0


def test_hybrid_escalates_to_gemini_when_local_low_confidence() -> None:
    local = _StubClient(_local_decision(0.4))
    gemini = _StubClient(_local_decision(0.95, priority="critical"))
    client = HybridInferenceClient(
        local_client=local,
        gemini_client=gemini,
        escalate_confidence_threshold=0.72,
    )
    out = client.analyze(np.zeros((5, 5, 3), dtype="uint8"), app_context={})
    assert out.confidence == 0.95
    assert client.last_source == "gemini"
    assert local.calls == 1
    assert gemini.calls == 1
