from __future__ import annotations

from screensense.config import load_settings
from screensense.integrations.voice import VoiceOutput, VoiceSettings


def main() -> None:
    settings = load_settings()
    voice = VoiceOutput(
        enabled=settings.enable_tts,
        settings=VoiceSettings(
            provider=settings.voice_provider,
            preset=settings.voice_preset,
            style=settings.voice_style,
            rate_wpm=settings.voice_rate_wpm,
            volume=settings.voice_volume,
            adaptive_mode=settings.voice_adaptive_mode,
            repeat_window_seconds=settings.voice_repeat_window_seconds,
            edge_voice=settings.voice_edge_name,
            edge_rate=settings.voice_edge_rate,
            edge_pitch=settings.voice_edge_pitch,
            coqui_model=settings.voice_coqui_model,
            coqui_speaker_wav=settings.voice_coqui_speaker_wav,
            coqui_language=settings.voice_coqui_language,
            coqui_device=settings.voice_coqui_device,
            piper_bin=settings.voice_piper_bin,
            piper_model_path=settings.voice_piper_model_path,
            piper_speaker_id=settings.voice_piper_speaker_id,
            piper_length_scale=settings.voice_piper_length_scale,
        ),
    )
    print(f"Voice provider resolved: {voice.provider}")
    voice.speak_event("Voice test successful. ARIA audio channel is online.", context="ARIA")
    print("Voice test call completed.")


if __name__ == "__main__":
    main()
