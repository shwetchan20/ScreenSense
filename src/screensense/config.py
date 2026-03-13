from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, cast

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    gemini_api_key: str
    gemini_model: str = "gemini-2.0-flash"
    assistant_name: str = "ARIA"
    assistant_persona: str = "calm concise proactive with dry wit"
    persona_learning_enabled: bool = True
    persona_profile_path: str = "runtime/persona_profile.json"
    app_adaptation_enabled: bool = True
    app_profile_path: str = "runtime/app_preferences.json"
    user_name: str = "Shwet"
    project_name: str = "ScreenSense"
    deadline_date: str = ""
    capture_interval_seconds: float = 3.0
    diff_threshold_percent: float = 35.0
    confidence_threshold: float = 0.80
    typing_idle_seconds: float = 2.0
    memory_max_items: int = 40
    inference_mode: Literal["local", "http"] = "local"
    inference_backend_url: str = "http://127.0.0.1:8080"
    inference_backend_auth_token: str = ""
    inference_timeout_seconds: float = 30.0
    reasoning_mode: Literal["gemini", "local", "hybrid"] = "hybrid"
    local_llm_provider: Literal["ollama", "none"] = "ollama"
    local_llm_model: str = "qwen2.5:latest"
    local_llm_base_url: str = "http://127.0.0.1:11434"
    local_llm_timeout_seconds: float = 25.0
    local_llm_use_vision: bool = True
    local_llm_escalate_confidence_threshold: float = 0.78
    hybrid_force_gemini_on_critical: bool = True
    enable_tts: bool = True
    voice_startup_greeting: bool = True
    voice_startup_message: str = "Online."
    voice_provider: Literal["auto", "pyttsx3", "edge_tts", "coqui_xtts", "piper"] = "auto"
    voice_preset: Literal["default", "astra_like"] = "default"
    voice_style: Literal["neutral", "friendly", "humorous"] = "neutral"
    voice_aggressiveness: Literal["quiet", "balanced", "chatty"] = "balanced"
    voice_rate_wpm: int = 175
    voice_volume: float = 1.0
    voice_adaptive_mode: bool = True
    voice_repeat_window_seconds: float = 120.0
    voice_edge_name: str = "en-IN-NeerjaNeural"
    voice_edge_rate: str = "+0%"
    voice_edge_pitch: str = "+0Hz"
    voice_coqui_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    voice_coqui_speaker_wav: str = ""
    voice_coqui_language: str = "en"
    voice_coqui_device: Literal["auto", "cpu", "cuda"] = "auto"
    voice_piper_bin: str = ""
    voice_piper_model_path: str = ""
    voice_piper_speaker_id: int = 0
    voice_piper_length_scale: float = 1.0
    enable_voice_input: bool = False
    voice_confirm_timeout_seconds: int = 4
    enable_remote_approval: bool = False
    remote_approval_provider: Literal["none", "telegram"] = "none"
    remote_approval_timeout_seconds: int = 90
    remote_approval_poll_seconds: float = 2.0
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    enable_remote_alerts: bool = False
    remote_alert_min_priority: Literal["critical", "helpful"] = "critical"
    remote_alert_cooldown_seconds: float = 300.0
    enable_actions: bool = False
    product_mode: Literal["observe", "ask", "allowlisted_auto"] = "observe"
    ask_before_act: bool = True
    interrupt_cooldown_seconds: float = 20.0
    dedupe_window_seconds: float = 180.0
    semantic_dedupe_window_seconds: float = 240.0
    max_interrupts_per_hour: int = 8
    quiet_hours_start: int = -1
    quiet_hours_end: int = -1
    audit_logging_enabled: bool = True
    audit_log_path: str = "runtime/audit.log.jsonl"
    audit_sink_mode: Literal["none", "local", "firestore", "dual"] = "local"
    memory_sink_mode: Literal["none", "local", "firestore", "dual"] = "local"
    firestore_project_id: str = ""
    firestore_database: str = "(default)"
    firestore_audit_collection: str = "screensense_audit"
    firestore_memory_collection: str = "screensense_memory"
    gemini_min_call_interval_seconds: float = 12.0
    gemini_max_calls_per_minute: int = 4
    focus_mode: bool = False
    app_title_blocklist: list[str] = field(default_factory=list)
    action_allowlist: list[str] = field(default_factory=lambda: ["clipboard_copy", "open_quick_fix"])
    auto_execute_max_risk: Literal["low", "medium", "high"] = "low"
    agent_runtime_mode: Literal["adk", "local"] = "adk"
    agent_runtime_strict: bool = False
    vision_error_threshold: int = 4
    vision_error_window_seconds: float = 120.0
    vision_circuit_open_seconds: float = 300.0
    away_idle_seconds: float = 300.0
    break_nudge_minutes: float = 90.0
    break_nudge_repeat_minutes: float = 90.0
    memory_local_path: str = "runtime/memory.log.jsonl"
    memory_sqlite_path: str = "runtime/aria_memory.db"
    fast_path_enabled: bool = True
    fast_path_user_active_diff_max: float = 22.0
    fast_path_app_revisit_seconds: float = 8.0
    fast_path_app_revisit_diff_max: float = 28.0
    enable_ocr_context: bool = True
    ocr_provider: Literal["auto", "none", "pytesseract"] = "auto"
    ocr_min_interval_seconds: float = 10.0
    ocr_max_text_chars: int = 280
    ui_automation_enabled: bool = True
    visual_only_apps: list[str] = field(
        default_factory=lambda: ["figma", "photoshop", "blender", "unity", "game", "games"]
    )
    enable_impact_scoring: bool = True
    impact_score_threshold: float = 0.55
    stale_decision_max_age_seconds: float = 8.0
    stale_decision_require_same_app: bool = True
    demo_force_speak: bool = False
    demo_force_infer_interval_seconds: float = 0.0


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_product_mode(value: str | None) -> Literal["observe", "ask", "allowlisted_auto"]:
    mode = (value or "observe").strip().lower()
    allowed = {"observe", "ask", "allowlisted_auto"}
    if mode not in allowed:
        raise ValueError(f"Invalid PRODUCT_MODE '{mode}'. Allowed: {sorted(allowed)}")
    return cast(Literal["observe", "ask", "allowlisted_auto"], mode)


def _parse_csv_tokens(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def _parse_risk(value: str | None) -> Literal["low", "medium", "high"]:
    risk = (value or "low").strip().lower()
    allowed = {"low", "medium", "high"}
    if risk not in allowed:
        raise ValueError(f"Invalid AUTO_EXECUTE_MAX_RISK '{risk}'. Allowed: {sorted(allowed)}")
    return cast(Literal["low", "medium", "high"], risk)


def _parse_agent_runtime_mode(value: str | None) -> Literal["adk", "local"]:
    mode = (value or "adk").strip().lower()
    allowed = {"adk", "local"}
    if mode not in allowed:
        raise ValueError(f"Invalid AGENT_RUNTIME_MODE '{mode}'. Allowed: {sorted(allowed)}")
    return cast(Literal["adk", "local"], mode)


def _parse_inference_mode(value: str | None) -> Literal["local", "http"]:
    mode = (value or "local").strip().lower()
    allowed = {"local", "http"}
    if mode not in allowed:
        raise ValueError(f"Invalid INFERENCE_MODE '{mode}'. Allowed: {sorted(allowed)}")
    return cast(Literal["local", "http"], mode)


def _parse_reasoning_mode(value: str | None) -> Literal["gemini", "local", "hybrid"]:
    mode = (value or "hybrid").strip().lower()
    allowed = {"gemini", "local", "hybrid"}
    if mode not in allowed:
        raise ValueError(f"Invalid REASONING_MODE '{mode}'. Allowed: {sorted(allowed)}")
    return cast(Literal["gemini", "local", "hybrid"], mode)


def _parse_local_llm_provider(value: str | None) -> Literal["ollama", "none"]:
    provider = (value or "ollama").strip().lower()
    allowed = {"ollama", "none"}
    if provider not in allowed:
        raise ValueError(f"Invalid LOCAL_LLM_PROVIDER '{provider}'. Allowed: {sorted(allowed)}")
    return cast(Literal["ollama", "none"], provider)


def _parse_voice_style(value: str | None) -> Literal["neutral", "friendly", "humorous"]:
    style = (value or "neutral").strip().lower()
    allowed = {"neutral", "friendly", "humorous"}
    if style not in allowed:
        raise ValueError(f"Invalid VOICE_STYLE '{style}'. Allowed: {sorted(allowed)}")
    return cast(Literal["neutral", "friendly", "humorous"], style)


def _parse_voice_preset(value: str | None) -> Literal["default", "astra_like"]:
    preset = (value or "default").strip().lower()
    allowed = {"default", "astra_like"}
    if preset not in allowed:
        raise ValueError(f"Invalid VOICE_PRESET '{preset}'. Allowed: {sorted(allowed)}")
    return cast(Literal["default", "astra_like"], preset)


def _parse_voice_aggressiveness(value: str | None) -> Literal["quiet", "balanced", "chatty"]:
    mode = (value or "balanced").strip().lower()
    allowed = {"quiet", "balanced", "chatty"}
    if mode not in allowed:
        raise ValueError(f"Invalid VOICE_AGGRESSIVENESS '{mode}'. Allowed: {sorted(allowed)}")
    return cast(Literal["quiet", "balanced", "chatty"], mode)


def _parse_voice_provider(
    value: str | None,
) -> Literal["auto", "pyttsx3", "edge_tts", "coqui_xtts", "piper"]:
    provider = (value or "auto").strip().lower()
    allowed = {"auto", "pyttsx3", "edge_tts", "coqui_xtts", "piper"}
    if provider not in allowed:
        raise ValueError(f"Invalid VOICE_PROVIDER '{provider}'. Allowed: {sorted(allowed)}")
    return cast(Literal["auto", "pyttsx3", "edge_tts", "coqui_xtts", "piper"], provider)


def _parse_voice_device(value: str | None) -> Literal["auto", "cpu", "cuda"]:
    device = (value or "auto").strip().lower()
    allowed = {"auto", "cpu", "cuda"}
    if device not in allowed:
        raise ValueError(f"Invalid VOICE_COQUI_DEVICE '{device}'. Allowed: {sorted(allowed)}")
    return cast(Literal["auto", "cpu", "cuda"], device)


def _parse_sink_mode(value: str | None) -> Literal["none", "local", "firestore", "dual"]:
    mode = (value or "local").strip().lower()
    allowed = {"none", "local", "firestore", "dual"}
    if mode not in allowed:
        raise ValueError(f"Invalid sink mode '{mode}'. Allowed: {sorted(allowed)}")
    return cast(Literal["none", "local", "firestore", "dual"], mode)


def _parse_remote_approval_provider(value: str | None) -> Literal["none", "telegram"]:
    provider = (value or "none").strip().lower()
    allowed = {"none", "telegram"}
    if provider not in allowed:
        raise ValueError(
            f"Invalid REMOTE_APPROVAL_PROVIDER '{provider}'. Allowed: {sorted(allowed)}"
        )
    return cast(Literal["none", "telegram"], provider)


def _parse_remote_alert_min_priority(value: str | None) -> Literal["critical", "helpful"]:
    level = (value or "critical").strip().lower()
    allowed = {"critical", "helpful"}
    if level not in allowed:
        raise ValueError(
            f"Invalid REMOTE_ALERT_MIN_PRIORITY '{level}'. Allowed: {sorted(allowed)}"
        )
    return cast(Literal["critical", "helpful"], level)


def _parse_ocr_provider(value: str | None) -> Literal["auto", "none", "pytesseract"]:
    provider = (value or "auto").strip().lower()
    allowed = {"auto", "none", "pytesseract"}
    if provider not in allowed:
        raise ValueError(f"Invalid OCR_PROVIDER '{provider}'. Allowed: {sorted(allowed)}")
    return cast(Literal["auto", "none", "pytesseract"], provider)


def load_settings() -> Settings:
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    voice_preset = _parse_voice_preset(os.getenv("VOICE_PRESET"))
    voice_provider_raw = os.getenv("VOICE_PROVIDER")
    voice_style_raw = os.getenv("VOICE_STYLE")
    voice_rate_raw = os.getenv("VOICE_RATE_WPM")
    edge_name_raw = os.getenv("VOICE_EDGE_NAME")
    edge_rate_raw = os.getenv("VOICE_EDGE_RATE")
    edge_pitch_raw = os.getenv("VOICE_EDGE_PITCH")

    # Preset only applies when caller did not explicitly set each value.
    if voice_preset == "astra_like":
        voice_provider = _parse_voice_provider(voice_provider_raw or "edge_tts")
        voice_style = _parse_voice_style(voice_style_raw or "friendly")
        voice_rate_wpm = int(voice_rate_raw or "182")
        voice_edge_name = (edge_name_raw or "en-US-JennyNeural").strip()
        voice_edge_rate = edge_rate_raw or "+8%"
        voice_edge_pitch = edge_pitch_raw or "+0Hz"
    else:
        voice_provider = _parse_voice_provider(voice_provider_raw)
        voice_style = _parse_voice_style(voice_style_raw)
        voice_rate_wpm = int(voice_rate_raw or "175")
        voice_edge_name = (edge_name_raw or "en-IN-NeerjaNeural").strip()
        voice_edge_rate = edge_rate_raw or "+0%"
        voice_edge_pitch = edge_pitch_raw or "+0Hz"

    return Settings(
        gemini_api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        assistant_name=os.getenv("ASSISTANT_NAME", "ARIA").strip(),
        assistant_persona=os.getenv(
            "ASSISTANT_PERSONA", "calm concise proactive with dry wit"
        ).strip(),
        persona_learning_enabled=_to_bool(os.getenv("PERSONA_LEARNING_ENABLED"), True),
        persona_profile_path=os.getenv("PERSONA_PROFILE_PATH", "runtime/persona_profile.json"),
        app_adaptation_enabled=_to_bool(os.getenv("APP_ADAPTATION_ENABLED"), True),
        app_profile_path=os.getenv("APP_PROFILE_PATH", "runtime/app_preferences.json"),
        user_name=os.getenv("USER_NAME", "Shwet").strip(),
        project_name=os.getenv("PROJECT_NAME", "ScreenSense").strip(),
        deadline_date=os.getenv("DEADLINE_DATE", "").strip(),
        capture_interval_seconds=float(os.getenv("CAPTURE_INTERVAL_SECONDS", "3")),
        diff_threshold_percent=float(os.getenv("DIFF_THRESHOLD", "35")),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.75")),
        typing_idle_seconds=float(os.getenv("TYPING_IDLE_SECONDS", "2.0")),
        memory_max_items=int(os.getenv("MEMORY_MAX_ITEMS", "40")),
        inference_mode=_parse_inference_mode(os.getenv("INFERENCE_MODE")),
        inference_backend_url=os.getenv("INFERENCE_BACKEND_URL", "http://127.0.0.1:8080"),
        inference_backend_auth_token=os.getenv("INFERENCE_BACKEND_AUTH_TOKEN", ""),
        inference_timeout_seconds=float(os.getenv("INFERENCE_TIMEOUT_SECONDS", "30")),
        reasoning_mode=_parse_reasoning_mode(os.getenv("REASONING_MODE")),
        local_llm_provider=_parse_local_llm_provider(os.getenv("LOCAL_LLM_PROVIDER")),
        local_llm_model=os.getenv("LOCAL_LLM_MODEL", "qwen2.5:latest").strip(),
        local_llm_base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").strip(),
        local_llm_timeout_seconds=float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "25")),
        local_llm_use_vision=_to_bool(os.getenv("LOCAL_LLM_USE_VISION"), True),
        local_llm_escalate_confidence_threshold=float(
            os.getenv("LOCAL_LLM_ESCALATE_CONFIDENCE_THRESHOLD", "0.72")
        ),
        hybrid_force_gemini_on_critical=_to_bool(
            os.getenv("HYBRID_FORCE_GEMINI_ON_CRITICAL"), True
        ),
        enable_tts=_to_bool(os.getenv("ENABLE_TTS"), True),
        voice_startup_greeting=_to_bool(os.getenv("VOICE_STARTUP_GREETING"), True),
        voice_startup_message=os.getenv("VOICE_STARTUP_MESSAGE", "Online.").strip(),
        voice_provider=voice_provider,
        voice_preset=voice_preset,
        voice_style=voice_style,
        voice_aggressiveness=_parse_voice_aggressiveness(os.getenv("VOICE_AGGRESSIVENESS")),
        voice_rate_wpm=voice_rate_wpm,
        voice_volume=float(os.getenv("VOICE_VOLUME", "1.0")),
        voice_adaptive_mode=_to_bool(os.getenv("VOICE_ADAPTIVE_MODE"), True),
        voice_repeat_window_seconds=float(os.getenv("VOICE_REPEAT_WINDOW_SECONDS", "120")),
        voice_edge_name=voice_edge_name,
        voice_edge_rate=voice_edge_rate,
        voice_edge_pitch=voice_edge_pitch,
        voice_coqui_model=os.getenv(
            "VOICE_COQUI_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2"
        ).strip(),
        voice_coqui_speaker_wav=os.getenv("VOICE_COQUI_SPEAKER_WAV", "").strip(),
        voice_coqui_language=os.getenv("VOICE_COQUI_LANGUAGE", "en").strip(),
        voice_coqui_device=_parse_voice_device(os.getenv("VOICE_COQUI_DEVICE")),
        voice_piper_bin=os.getenv("VOICE_PIPER_BIN", "").strip(),
        voice_piper_model_path=os.getenv("VOICE_PIPER_MODEL_PATH", "").strip(),
        voice_piper_speaker_id=int(os.getenv("VOICE_PIPER_SPEAKER_ID", "0")),
        voice_piper_length_scale=float(os.getenv("VOICE_PIPER_LENGTH_SCALE", "1.0")),
        enable_voice_input=_to_bool(os.getenv("ENABLE_VOICE_INPUT"), False),
        voice_confirm_timeout_seconds=int(os.getenv("VOICE_CONFIRM_TIMEOUT_SECONDS", "4")),
        enable_remote_approval=_to_bool(os.getenv("ENABLE_REMOTE_APPROVAL"), False),
        remote_approval_provider=_parse_remote_approval_provider(
            os.getenv("REMOTE_APPROVAL_PROVIDER")
        ),
        remote_approval_timeout_seconds=int(os.getenv("REMOTE_APPROVAL_TIMEOUT_SECONDS", "90")),
        remote_approval_poll_seconds=float(os.getenv("REMOTE_APPROVAL_POLL_SECONDS", "2.0")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        enable_remote_alerts=_to_bool(os.getenv("ENABLE_REMOTE_ALERTS"), False),
        remote_alert_min_priority=_parse_remote_alert_min_priority(
            os.getenv("REMOTE_ALERT_MIN_PRIORITY")
        ),
        remote_alert_cooldown_seconds=float(os.getenv("REMOTE_ALERT_COOLDOWN_SECONDS", "300")),
        enable_actions=_to_bool(os.getenv("ENABLE_ACTIONS"), False),
        product_mode=_parse_product_mode(os.getenv("PRODUCT_MODE")),
        ask_before_act=_to_bool(os.getenv("ASK_BEFORE_ACT"), True),
        interrupt_cooldown_seconds=float(os.getenv("INTERRUPT_COOLDOWN_SECONDS", "20")),
        dedupe_window_seconds=float(os.getenv("DEDUPE_WINDOW_SECONDS", "180")),
        semantic_dedupe_window_seconds=float(os.getenv("SEMANTIC_DEDUPE_WINDOW_SECONDS", "240")),
        max_interrupts_per_hour=int(os.getenv("MAX_INTERRUPTS_PER_HOUR", "8")),
        quiet_hours_start=int(os.getenv("QUIET_HOURS_START", "-1")),
        quiet_hours_end=int(os.getenv("QUIET_HOURS_END", "-1")),
        audit_logging_enabled=_to_bool(os.getenv("AUDIT_LOGGING_ENABLED"), True),
        audit_log_path=os.getenv("AUDIT_LOG_PATH", "runtime/audit.log.jsonl"),
        audit_sink_mode=_parse_sink_mode(os.getenv("AUDIT_SINK_MODE")),
        memory_sink_mode=_parse_sink_mode(os.getenv("MEMORY_SINK_MODE")),
        firestore_project_id=os.getenv("FIRESTORE_PROJECT_ID", "").strip(),
        firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)").strip(),
        firestore_audit_collection=os.getenv(
            "FIRESTORE_AUDIT_COLLECTION", "screensense_audit"
        ).strip(),
        firestore_memory_collection=os.getenv(
            "FIRESTORE_MEMORY_COLLECTION", "screensense_memory"
        ).strip(),
        gemini_min_call_interval_seconds=float(
            os.getenv("GEMINI_MIN_CALL_INTERVAL_SECONDS", "12")
        ),
        gemini_max_calls_per_minute=int(os.getenv("GEMINI_MAX_CALLS_PER_MINUTE", "4")),
        focus_mode=_to_bool(os.getenv("FOCUS_MODE"), False),
        app_title_blocklist=_parse_csv_tokens(os.getenv("APP_TITLE_BLOCKLIST")),
        action_allowlist=_parse_csv_tokens(os.getenv("ACTION_ALLOWLIST"))
        or ["clipboard_copy", "open_quick_fix"],
        auto_execute_max_risk=_parse_risk(os.getenv("AUTO_EXECUTE_MAX_RISK")),
        agent_runtime_mode=_parse_agent_runtime_mode(os.getenv("AGENT_RUNTIME_MODE")),
        agent_runtime_strict=_to_bool(os.getenv("AGENT_RUNTIME_STRICT"), False),
        vision_error_threshold=int(os.getenv("VISION_ERROR_THRESHOLD", "4")),
        vision_error_window_seconds=float(os.getenv("VISION_ERROR_WINDOW_SECONDS", "120")),
        vision_circuit_open_seconds=float(os.getenv("VISION_CIRCUIT_OPEN_SECONDS", "300")),
        away_idle_seconds=float(os.getenv("AWAY_IDLE_SECONDS", "300")),
        break_nudge_minutes=float(os.getenv("BREAK_NUDGE_MINUTES", "90")),
        break_nudge_repeat_minutes=float(os.getenv("BREAK_NUDGE_REPEAT_MINUTES", "90")),
        memory_local_path=os.getenv("MEMORY_LOCAL_PATH", "runtime/memory.log.jsonl"),
        memory_sqlite_path=os.getenv("MEMORY_SQLITE_PATH", "runtime/aria_memory.db"),
        fast_path_enabled=_to_bool(os.getenv("FAST_PATH_ENABLED"), True),
        fast_path_user_active_diff_max=float(os.getenv("FAST_PATH_USER_ACTIVE_DIFF_MAX", "22")),
        fast_path_app_revisit_seconds=float(os.getenv("FAST_PATH_APP_REVISIT_SECONDS", "8")),
        fast_path_app_revisit_diff_max=float(os.getenv("FAST_PATH_APP_REVISIT_DIFF_MAX", "28")),
        enable_ocr_context=_to_bool(os.getenv("ENABLE_OCR_CONTEXT"), True),
        ocr_provider=_parse_ocr_provider(os.getenv("OCR_PROVIDER")),
        ocr_min_interval_seconds=float(os.getenv("OCR_MIN_INTERVAL_SECONDS", "10")),
        ocr_max_text_chars=int(os.getenv("OCR_MAX_TEXT_CHARS", "280")),
        ui_automation_enabled=_to_bool(os.getenv("UI_AUTOMATION_ENABLED"), True),
        visual_only_apps=_parse_csv_tokens(
            os.getenv(
                "VISUAL_ONLY_APPS",
                "figma,photoshop,blender,unity,game,games",
            )
        ),
        enable_impact_scoring=_to_bool(os.getenv("ENABLE_IMPACT_SCORING"), True),
        impact_score_threshold=float(os.getenv("IMPACT_SCORE_THRESHOLD", "0.62")),
        stale_decision_max_age_seconds=float(os.getenv("STALE_DECISION_MAX_AGE_SECONDS", "8")),
        stale_decision_require_same_app=_to_bool(
            os.getenv("STALE_DECISION_REQUIRE_SAME_APP"), True
        ),
        demo_force_speak=_to_bool(os.getenv("DEMO_FORCE_SPEAK"), False),
        demo_force_infer_interval_seconds=float(
            os.getenv("DEMO_FORCE_INFER_INTERVAL_SECONDS", "0")
        ),
    )
