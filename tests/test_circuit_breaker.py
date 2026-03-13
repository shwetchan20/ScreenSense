from screensense.core.circuit_breaker import VisionCircuitBreaker


def test_circuit_breaker_opens_after_threshold_errors() -> None:
    breaker = VisionCircuitBreaker(error_threshold=2, error_window_seconds=60, open_duration_seconds=30)
    first = breaker.record_error()
    second = breaker.record_error()
    assert first.reason == "error_recorded"
    assert second.reason == "vision_circuit_opened"
    check = breaker.check()
    assert not check.allow
    assert check.reason == "vision_circuit_open"


def test_circuit_breaker_allows_when_closed() -> None:
    breaker = VisionCircuitBreaker(error_threshold=3, error_window_seconds=60, open_duration_seconds=30)
    check = breaker.check()
    assert check.allow
    assert check.reason == "closed"

