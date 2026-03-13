import numpy as np

from screensense.inference.local_qwen import LocalQwenInferenceClient


def test_local_qwen_falls_back_when_provider_disabled() -> None:
    client = LocalQwenInferenceClient(
        provider="none",
        model="qwen2.5:latest",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=1.0,
        ui_context_extractor=None,
    )
    decision = client.analyze(
        frame_rgb=np.zeros((6, 6, 3), dtype="uint8"),
        app_context={"window_title": "Visual Studio Code"},
    )
    assert decision.priority == "silent"
    assert not decision.should_interrupt
