from pathlib import Path

from screensense.core.persona import PersonaAdapter
from screensense.models import VisionDecision


def test_persona_feedback_updates_profile_and_persists(tmp_path: Path) -> None:
    profile_path = tmp_path / "persona.json"
    adapter = PersonaAdapter(
        enabled=True,
        path=str(profile_path),
        assistant_name="ARIA",
        user_name="Shwet",
        base_persona="calm concise proactive with dry wit",
    )
    initial = adapter.profile.trust_score
    adapter.record_feedback(event="action_executed")
    assert adapter.profile.trust_score > initial
    assert profile_path.exists()


def test_persona_composes_personalized_message() -> None:
    adapter = PersonaAdapter(
        enabled=True,
        path="runtime/test_persona_profile.json",
        assistant_name="ARIA",
        user_name="Shwet",
        base_persona="calm concise proactive with dry wit",
    )
    decision = VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.9,
        message="Tests are failing in the auth module.",
        can_fix=True,
        priority="helpful",
        domain="code",
    )
    message = adapter.compose_message(
        decision=decision,
        goal="Ship stable code and clear active bugs",
        base_message="Shwet, tests are failing.",
    )
    assert "Shwet" in message
    assert "Ship stable code and clear active bugs" in message
