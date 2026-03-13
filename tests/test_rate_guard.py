import time

from screensense.core.rate_guard import GeminiRateGuard


def test_rate_guard_allows_first_call() -> None:
    guard = GeminiRateGuard(min_interval_seconds=10.0, max_calls_per_minute=2)
    result = guard.check()
    assert result.allowed


def test_rate_guard_enforces_min_interval() -> None:
    guard = GeminiRateGuard(min_interval_seconds=10.0, max_calls_per_minute=5)
    first = guard.check()
    second = guard.check()
    assert first.allowed
    assert not second.allowed
    assert second.reason == "min_interval_guard"
    assert second.retry_after_seconds > 0


def test_rate_guard_enforces_max_calls_per_minute() -> None:
    guard = GeminiRateGuard(min_interval_seconds=0.0, max_calls_per_minute=2)
    first = guard.check()
    second = guard.check()
    third = guard.check()
    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.reason == "max_calls_per_minute_guard"


def test_rate_guard_recovers_after_one_minute_window() -> None:
    guard = GeminiRateGuard(min_interval_seconds=0.0, max_calls_per_minute=1)
    first = guard.check()
    assert first.allowed
    # Simulate window passing by mutating internal state timestamp.
    guard._calls_last_minute[0] = time.time() - 61.0  # type: ignore[attr-defined]
    second = guard.check()
    assert second.allowed

