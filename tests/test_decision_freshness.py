import time

from screensense.core.decision_freshness import is_stale_decision


def test_decision_is_stale_by_age() -> None:
    stale, reason = is_stale_decision(
        submitted_ts=time.time() - 20,
        max_age_seconds=8,
        submitted_app_key="code.exe|vscode",
        current_app_key="code.exe|vscode",
        require_same_app=True,
    )
    assert stale
    assert reason == "stale_age"


def test_decision_is_stale_by_app_switch() -> None:
    stale, reason = is_stale_decision(
        submitted_ts=time.time(),
        max_age_seconds=30,
        submitted_app_key="code.exe|vscode",
        current_app_key="chrome.exe|docs",
        require_same_app=True,
    )
    assert stale
    assert reason == "stale_app_switched"


def test_decision_is_fresh_when_recent_and_same_app() -> None:
    stale, reason = is_stale_decision(
        submitted_ts=time.time(),
        max_age_seconds=30,
        submitted_app_key="code.exe|vscode",
        current_app_key="code.exe|vscode",
        require_same_app=True,
    )
    assert not stale
    assert reason == "fresh"
