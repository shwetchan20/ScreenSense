from screensense.integrations.gemini_client import GeminiVisionClient


def test_format_context_includes_window_and_process_fields() -> None:
    text = GeminiVisionClient._format_context(
        {
            "window_title": "Visual Studio Code",
            "process_name": "Code.exe",
            "executable_name": "Code.exe",
            "pid": 1234,
        }
    )
    assert "Visual Studio Code" in text
    assert "Code.exe" in text
    assert "1234" in text

