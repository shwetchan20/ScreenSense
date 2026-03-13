from screensense.core.fast_path import FastPathGate


def test_fast_path_skips_when_user_active_and_low_signal() -> None:
    gate = FastPathGate(
        enabled=True,
        user_active_diff_max=20.0,
        app_revisit_seconds=8.0,
        app_revisit_diff_max=28.0,
    )
    reason = gate.should_skip(user_idle=False, changed_percent=12.0, app_key="code|vscode")
    assert reason == "fast_path_user_active_low_signal"


def test_fast_path_skips_same_app_revisit_after_recent_submit() -> None:
    gate = FastPathGate(
        enabled=True,
        user_active_diff_max=20.0,
        app_revisit_seconds=30.0,
        app_revisit_diff_max=30.0,
    )
    gate.note_inference_submitted("code|vscode")
    reason = gate.should_skip(user_idle=True, changed_percent=15.0, app_key="code|vscode")
    assert reason == "fast_path_same_app_revisit"


def test_fast_path_allows_high_signal_when_user_active() -> None:
    gate = FastPathGate(
        enabled=True,
        user_active_diff_max=20.0,
        app_revisit_seconds=8.0,
        app_revisit_diff_max=28.0,
    )
    reason = gate.should_skip(user_idle=False, changed_percent=65.0, app_key="code|vscode")
    assert reason is None
