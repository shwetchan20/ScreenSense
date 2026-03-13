"""Quick voice test for ARIA"""

from src.screensense.config import load_settings
from src.screensense.integrations.voice import VoiceOutput, VoiceSettings

print("Testing ARIA voice output...")
print("")

settings = load_settings()

voice = VoiceOutput(
    enabled=True,
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
    ),
)

print(f"Voice provider: {voice.provider}")
print(f"Voice: {settings.voice_edge_name}")
print("")

print("Speaking test message...")
voice.speak("ARIA is now online and ready to assist you with verified perception.")

print("")
print("✓ Voice test complete!")
