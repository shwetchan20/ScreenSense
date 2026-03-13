from screensense.core.goal_engine import GoalEngine
from screensense.core.presence import PresenceEngine
from screensense.models import VisionDecision


def test_presence_snapshot_has_time_and_goal() -> None:
    engine = PresenceEngine(
        assistant_name="ARIA",
        assistant_persona="calm concise proactive with dry wit",
        user_name="Shwet",
        project_name="ScreenSense",
        deadline_date="",
        away_idle_seconds=300,
        break_nudge_minutes=999,
        break_nudge_repeat_minutes=999,
    )
    snap = engine.snapshot(goal="Ship stable code", memory_digest="vscode:5")
    assert snap.goal == "Ship stable code"
    assert snap.session_minutes >= 0
    assert snap.time_block in {"morning", "afternoon", "evening", "late_night"}


def test_presence_compose_spoken_message_adds_identity_and_goal() -> None:
    engine = PresenceEngine(
        assistant_name="ARIA",
        assistant_persona="calm concise proactive with dry wit",
        user_name="Shwet",
        project_name="ScreenSense",
        deadline_date="",
        away_idle_seconds=300,
        break_nudge_minutes=999,
        break_nudge_repeat_minutes=999,
    )
    decision = VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.95,
        message="Type error detected on line 10.",
        can_fix=True,
        priority="helpful",
        domain="code",
    )
    spoken = engine.compose_spoken_message(decision, goal="Ship stable code and clear active bugs")
    assert "Shwet" in spoken
    assert "Type error detected on line 10." in spoken
    assert "Current objective" in spoken


def test_goal_engine_tracks_code_goal() -> None:
    engine = GoalEngine()
    decision = VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.9,
        message="Traceback detected in tests.",
        can_fix=True,
        priority="helpful",
        domain="code",
    )
    goal = engine.update(decision, active_window_title="Project - VSCode")
    assert "code" in goal.lower() or "bug" in goal.lower()
