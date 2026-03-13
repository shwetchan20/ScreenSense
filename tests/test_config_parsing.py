from screensense.config import (
    _parse_inference_mode,
    _parse_agent_runtime_mode,
    _parse_csv_tokens,
    _parse_local_llm_provider,
    _parse_ocr_provider,
    _parse_reasoning_mode,
    _parse_remote_alert_min_priority,
    _parse_remote_approval_provider,
    _parse_sink_mode,
    _parse_voice_provider,
    _parse_voice_preset,
    _parse_voice_aggressiveness,
    _parse_voice_style,
)


def test_parse_csv_tokens_trims_and_normalizes() -> None:
    assert _parse_csv_tokens(" Genshin Impact,  Steam ") == ["genshin impact", "steam"]


def test_parse_csv_tokens_handles_none() -> None:
    assert _parse_csv_tokens(None) == []


def test_parse_agent_runtime_mode_accepts_adk() -> None:
    assert _parse_agent_runtime_mode("adk") == "adk"


def test_parse_voice_style_accepts_humorous() -> None:
    assert _parse_voice_style("humorous") == "humorous"


def test_parse_voice_aggressiveness_accepts_chatty() -> None:
    assert _parse_voice_aggressiveness("chatty") == "chatty"


def test_parse_voice_provider_accepts_edge_tts() -> None:
    assert _parse_voice_provider("edge_tts") == "edge_tts"


def test_parse_voice_provider_accepts_coqui_xtts() -> None:
    assert _parse_voice_provider("coqui_xtts") == "coqui_xtts"


def test_parse_voice_preset_accepts_astra_like() -> None:
    assert _parse_voice_preset("astra_like") == "astra_like"


def test_parse_inference_mode_accepts_http() -> None:
    assert _parse_inference_mode("http") == "http"


def test_parse_sink_mode_accepts_dual() -> None:
    assert _parse_sink_mode("dual") == "dual"


def test_parse_remote_approval_provider_accepts_telegram() -> None:
    assert _parse_remote_approval_provider("telegram") == "telegram"


def test_parse_remote_alert_min_priority_accepts_helpful() -> None:
    assert _parse_remote_alert_min_priority("helpful") == "helpful"


def test_parse_ocr_provider_accepts_pytesseract() -> None:
    assert _parse_ocr_provider("pytesseract") == "pytesseract"


def test_parse_reasoning_mode_accepts_hybrid() -> None:
    assert _parse_reasoning_mode("hybrid") == "hybrid"


def test_parse_local_llm_provider_accepts_ollama() -> None:
    assert _parse_local_llm_provider("ollama") == "ollama"
