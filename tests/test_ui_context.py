import numpy as np

from screensense.core.ui_context import UiContextExtractor, UiContextSettings, clean_ocr_text


def test_clean_ocr_text_normalizes_whitespace_and_truncates() -> None:
    raw = "Hello \n\n world\tfrom   OCR " * 20
    cleaned = clean_ocr_text(raw, max_chars=40)
    assert "\n" not in cleaned
    assert "\t" not in cleaned
    assert len(cleaned) <= 43


def test_ui_context_extractor_disables_when_provider_none() -> None:
    extractor = UiContextExtractor(
        UiContextSettings(
            enabled=True,
            provider="none",
            min_interval_seconds=1.0,
            max_text_chars=120,
        )
    )
    context = extractor.enrich(
        frame_rgb=np.zeros((10, 10, 3), dtype="uint8"),
        app_context={"window_title": "VS Code"},
    )
    assert context["ui_ocr_enabled"] is True
    assert context["ui_ocr_provider"] == "none"
    assert "ui_text_excerpt" not in context
