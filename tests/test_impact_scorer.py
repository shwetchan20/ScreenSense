from screensense.core.impact_scorer import ImpactScorer
from screensense.models import VisionDecision


def _decision() -> VisionDecision:
    return VisionDecision(
        context="VS Code",
        should_interrupt=True,
        confidence=0.9,
        message="Type error detected in test run.",
        can_fix=True,
        priority="helpful",
        domain="code",
    )


def test_impact_scorer_allows_high_value_interrupt() -> None:
    scorer = ImpactScorer(enabled=True, threshold=0.62)
    result = scorer.evaluate(
        decision=_decision(),
        changed_percent=32.0,
        user_idle=True,
        away=False,
        session_minutes=45,
    )
    assert result.allow_interrupt
    assert result.score >= 0.62


def test_impact_scorer_blocks_low_value_interrupt() -> None:
    scorer = ImpactScorer(enabled=True, threshold=0.62)
    d = _decision()
    d.should_interrupt = False
    d.priority = "silent"
    d.can_fix = False
    d.confidence = 0.3
    result = scorer.evaluate(
        decision=d,
        changed_percent=1.0,
        user_idle=False,
        away=False,
        session_minutes=5,
    )
    assert not result.allow_interrupt
    assert result.reason == "impact_below_threshold"
