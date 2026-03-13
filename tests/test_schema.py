from screensense.models import VisionDecision


def test_schema_accepts_valid_payload() -> None:
    payload = {
        "context": "VS Code · Python",
        "should_interrupt": True,
        "confidence": 0.91,
        "message": "TypeError on line 10.",
        "can_fix": True,
        "domain": "code",
        "proposed_action": "Open quick fix and patch argument type.",
    }
    obj = VisionDecision.model_validate(payload)
    assert obj.domain == "code"
    assert obj.confidence > 0.9

