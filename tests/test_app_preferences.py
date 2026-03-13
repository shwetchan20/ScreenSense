from pathlib import Path

from screensense.core.app_preferences import AppPreferenceStore, normalize_app_key


def test_app_preference_threshold_adjusts_after_denial(tmp_path: Path) -> None:
    store = AppPreferenceStore(enabled=True, path=str(tmp_path / "apps.json"))
    app_key = normalize_app_key("code.exe", "Visual Studio Code")
    base = 0.62
    before = store.threshold_for(base_threshold=base, app_key=app_key)
    store.record_feedback(app_key=app_key, event="action_denied")
    after = store.threshold_for(base_threshold=base, app_key=app_key)
    assert after > before


def test_app_preference_persists_to_disk(tmp_path: Path) -> None:
    path = tmp_path / "apps.json"
    app_key = normalize_app_key("chrome.exe", "Docs")
    store = AppPreferenceStore(enabled=True, path=str(path))
    store.record_feedback(app_key=app_key, event="action_executed")
    loaded = AppPreferenceStore(enabled=True, path=str(path))
    snap = loaded.snapshot(app_key)
    assert snap["samples"] >= 1
