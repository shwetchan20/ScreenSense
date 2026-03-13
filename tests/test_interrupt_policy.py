from screensense.core.interrupt_policy import InterruptPolicy
from screensense.models import VisionDecision


def _base_decision() -> VisionDecision:
    return VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.9,
        message="Type error spotted",
        can_fix=True,
        priority="helpful",
        domain="code",
    )


def test_policy_blocks_low_confidence() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=0.0,
        dedupe_window_seconds=60.0,
    )
    decision = _base_decision()
    decision.confidence = 0.5
    result = policy.evaluate(decision, user_idle=True)
    assert not result.allow_interrupt
    assert result.reason == "low_confidence"


def test_policy_applies_global_cooldown() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=60.0,
        dedupe_window_seconds=0.0,
    )
    decision = _base_decision()
    first = policy.evaluate(decision, user_idle=True)
    second = policy.evaluate(decision, user_idle=True)
    assert first.allow_interrupt
    assert not second.allow_interrupt
    assert second.reason == "global_cooldown"


def test_policy_suppresses_duplicates() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=0.0,
        dedupe_window_seconds=60.0,
    )
    decision = _base_decision()
    first = policy.evaluate(decision, user_idle=True)
    second = policy.evaluate(decision, user_idle=True)
    assert first.allow_interrupt
    assert not second.allow_interrupt
    assert second.reason == "duplicate_suppressed"


def test_policy_respects_silent_priority() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=0.0,
        dedupe_window_seconds=0.0,
    )
    decision = _base_decision()
    decision.priority = "silent"
    result = policy.evaluate(decision, user_idle=True)
    assert not result.allow_interrupt
    assert result.reason == "priority_silent"


def test_policy_suppresses_semantic_duplicates_for_paraphrased_messages() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=0.0,
        dedupe_window_seconds=0.0,
        semantic_dedupe_window_seconds=120.0,
    )
    first = _base_decision()
    first.message = "Code review warning: proposed changes may include duplicate function definition."
    second = _base_decision()
    second.message = "AI code review detected issue in proposed changes; review carefully."
    first_result = policy.evaluate(first, user_idle=True)
    second_result = policy.evaluate(second, user_idle=True)
    assert first_result.allow_interrupt
    assert not second_result.allow_interrupt
    assert second_result.reason == "semantic_duplicate_suppressed"


def test_policy_enforces_interrupt_budget() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=0.0,
        dedupe_window_seconds=0.0,
        max_interrupts_per_hour=1,
    )
    first = policy.evaluate(_base_decision(), user_idle=True)
    second = policy.evaluate(_base_decision(), user_idle=True)
    assert first.allow_interrupt
    assert not second.allow_interrupt
    assert second.reason == "interrupt_budget_exhausted"


def test_policy_respects_quiet_hours_for_non_critical() -> None:
    policy = InterruptPolicy(
        confidence_threshold=0.8,
        interrupt_cooldown_seconds=0.0,
        dedupe_window_seconds=0.0,
        quiet_hours_start=0,
        quiet_hours_end=0,
    )
    decision = _base_decision()
    result = policy.evaluate(decision, user_idle=True)
    assert not result.allow_interrupt
    assert result.reason == "quiet_hours"
