from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Literal

try:
    import winsound
except Exception:  # pragma: no cover
    winsound = None  # type: ignore[assignment]

import pyttsx3

try:
    import edge_tts
except Exception:  # pragma: no cover
    edge_tts = None  # type: ignore[assignment]

try:
    from playsound import playsound
except Exception:  # pragma: no cover
    playsound = None  # type: ignore[assignment]

try:
    from TTS.api import TTS as CoquiTTS
except Exception:  # pragma: no cover
    CoquiTTS = None  # type: ignore[assignment]

try:
    import torch
except Exception:  # pragma: no cover
    torch = None  # type: ignore[assignment]

try:
    import speech_recognition as sr
except Exception:  # pragma: no cover
    sr = None  # type: ignore[assignment]


@dataclass(slots=True)
class VoiceSettings:
    provider: Literal["auto", "pyttsx3", "edge_tts", "coqui_xtts", "piper"] = "auto"
    preset: Literal["default", "astra_like"] = "default"
    style: Literal["neutral", "friendly", "humorous"] = "neutral"
    rate_wpm: int = 175
    volume: float = 1.0
    adaptive_mode: bool = True
    repeat_window_seconds: float = 120.0
    edge_voice: str = "en-IN-NeerjaNeural"
    edge_rate: str = "+0%"
    edge_pitch: str = "+0Hz"
    coqui_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    coqui_speaker_wav: str = ""
    coqui_language: str = "en"
    coqui_device: Literal["auto", "cpu", "cuda"] = "auto"
    piper_bin: str = ""
    piper_model_path: str = ""
    piper_speaker_id: int = 0
    piper_length_scale: float = 1.0


def stylize_message(
    text: str,
    style: Literal["neutral", "friendly", "humorous"],
    *,
    preset: Literal["default", "astra_like"] = "default",
    context: str | None = None,
    confidence: float | None = None,
    adaptive_mode: bool = True,
) -> str:
    content = text.strip()
    if not content:
        return ""
    prefix = ""
    suffix = ""
    if adaptive_mode:
        if context:
            prefix = f"{context}. "
        if confidence is not None and confidence < 0.8:
            suffix = " I might be wrong, so double-check before acting."
    if preset == "astra_like":
        # Keep delivery short, calm, and intentionally non-gimmicky.
        if style == "humorous":
            style = "friendly"
        return f"{prefix}{content}{suffix}".strip()
    if style == "friendly":
        intros = [
            "Quick heads up.",
            "Small update.",
            "Just a quick nudge.",
        ]
        intro = intros[_stable_index(content, len(intros))]
        return f"{prefix}{intro} {content} Want me to help?{suffix}"
    if style == "humorous":
        intros = [
            "Mini chaos alert.",
            "Quick reality check.",
            "Side quest detected.",
            "Your friendly co-pilot reports:",
        ]
        outro = [
            "Should I swoop in and help?",
            "Want me to fix it before it grows legs?",
            "Need backup?",
        ]
        intro = intros[_stable_index(content + ":intro", len(intros))]
        tail = outro[_stable_index(content + ":tail", len(outro))]
        return f"{prefix}{intro} {content} {tail}{suffix}"
    return f"{prefix}{content}{suffix}".strip()


def _stable_index(seed: str, size: int) -> int:
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % max(1, size)


def parse_yes_no_intent(text: str) -> bool | None:
    normalized = re.sub(r"[^a-z0-9\s]+", " ", text.lower()).strip()
    tokens = set(normalized.split())
    yes_tokens = {"yes", "yeah", "yup", "sure", "ok", "okay", "approve", "proceed", "do"}
    no_tokens = {"no", "nope", "nah", "stop", "cancel", "deny", "dont", "don't"}
    if tokens & no_tokens:
        return False
    if tokens & yes_tokens:
        return True
    if "do it" in normalized:
        return True
    return None


class VoiceOutput:
    def __init__(self, enabled: bool = True, settings: VoiceSettings | None = None) -> None:
        self._enabled = enabled
        self._settings = settings or VoiceSettings()
        self._provider = self._resolve_provider()
        self._engine = None
        if enabled and self._provider == "pyttsx3":
            try:
                self._engine = pyttsx3.init()
            except Exception:
                self._engine = None
                if edge_tts is not None and playsound is not None:
                    self._provider = "edge_tts"
                elif self._can_use_piper():
                    self._provider = "piper"
        self._coqui_engine = None
        self._last_fingerprint = ""
        self._last_spoken_ts = 0.0
        self._lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None
        if self._engine is not None:
            self._engine.setProperty("rate", max(120, min(240, self._settings.rate_wpm)))
            self._engine.setProperty("volume", max(0.2, min(1.0, self._settings.volume)))

    def speak(self, text: str) -> None:
        self.speak_event(text)

    def speak_event(
        self,
        text: str,
        *,
        context: str | None = None,
        confidence: float | None = None,
    ) -> None:
        self.speak_mode(text, mode="speak", context=context, confidence=confidence)

    def speak_mode(
        self,
        text: str,
        *,
        mode: Literal["earcon", "whisper", "speak"],
        context: str | None = None,
        confidence: float | None = None,
    ) -> None:
        if not self._enabled or not text:
            return
        if mode == "earcon":
            self._play_earcon()
            return
        styled = stylize_message(
            text,
            self._settings.style,
            preset=self._settings.preset,
            context=context,
            confidence=confidence,
            adaptive_mode=self._settings.adaptive_mode,
        )
        if self._should_suppress_repeat(styled):
            return
        self._speak_with_profile(styled, mode=mode)
        self._remember(styled)

    @property
    def provider(self) -> Literal["pyttsx3", "edge_tts", "coqui_xtts", "piper"]:
        return self._provider

    def _resolve_provider(self) -> Literal["pyttsx3", "edge_tts", "coqui_xtts", "piper"]:
        if self._settings.provider == "pyttsx3":
            return "pyttsx3"
        if self._settings.provider == "coqui_xtts":
            if self._can_use_coqui():
                return "coqui_xtts"
            return "pyttsx3"
        if self._settings.provider == "piper":
            if self._can_use_piper():
                return "piper"
            return "pyttsx3"
        if self._settings.provider == "edge_tts":
            if edge_tts is not None and playsound is not None:
                return "edge_tts"
            return "pyttsx3"
        if self._can_use_coqui():
            return "coqui_xtts"
        if edge_tts is not None and playsound is not None:
            return "edge_tts"
        if self._can_use_piper():
            return "piper"
        return "pyttsx3"

    def _speak_with_provider(self, text: str) -> None:
        if self._provider == "coqui_xtts":
            if not self._speak_coqui(text):
                if self._settings.provider == "coqui_xtts":
                    return
                self._speak_fallback(text)
            return
        if self._provider == "edge_tts":
            if not self._speak_edge_tts(text):
                if self._settings.provider == "edge_tts":
                    return
                self._speak_fallback(text)
            return
        if self._provider == "piper":
            if not self._speak_piper(text):
                if self._settings.provider == "piper":
                    return
                self._speak_fallback(text)
            return
        if self._engine is None:
            self._speak_fallback(text)
            return
        self._speak_pyttsx3(text)

    def _speak_with_profile(self, text: str, *, mode: Literal["earcon", "whisper", "speak"]) -> None:
        if mode == "speak":
            self._speak_with_provider(text)
            return
        if mode == "whisper":
            original_rate = self._settings.edge_rate
            original_pitch = self._settings.edge_pitch
            original_volume = self._settings.volume
            try:
                self._settings.edge_rate = "-10%"
                self._settings.edge_pitch = "-5Hz"
                self._settings.volume = max(0.4, min(1.0, original_volume * 0.6))
                if self._engine is not None:
                    self._engine.setProperty("rate", max(120, min(200, int(self._settings.rate_wpm * 0.9))))
                    self._engine.setProperty("volume", self._settings.volume)
                self._speak_with_provider(text)
            finally:
                self._settings.edge_rate = original_rate
                self._settings.edge_pitch = original_pitch
                self._settings.volume = original_volume
                if self._engine is not None:
                    self._engine.setProperty("rate", max(120, min(240, self._settings.rate_wpm)))
                    self._engine.setProperty("volume", max(0.2, min(1.0, original_volume)))
            return
        self._speak_with_provider(text)

    def _play_earcon(self) -> None:
        if winsound is not None:
            try:
                winsound.Beep(740, 120)
                winsound.Beep(940, 120)
                return
            except Exception:
                pass
        # Fallback: short low-volume spoken chime
        self._speak_with_profile("chime", mode="whisper")

    def _speak_fallback(self, text: str) -> None:
        if self._speak_edge_tts(text):
            return
        if self._speak_piper(text):
            return
        self._speak_pyttsx3(text)

    def _speak_pyttsx3(self, text: str) -> None:
        if self._engine is None:
            return
        self._engine.say(text)
        self._engine.runAndWait()

    def _speak_edge_tts(self, text: str) -> bool:
        if edge_tts is None or playsound is None:
            return False
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp_path = tmp.name
            communicate = edge_tts.Communicate(
                text=text,
                voice=self._settings.edge_voice,
                rate=self._settings.edge_rate,
                pitch=self._settings.edge_pitch,
            )
            asyncio.run(communicate.save(tmp_path))
            playsound(tmp_path)
            return True
        except Exception:
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _speak_coqui(self, text: str) -> bool:
        if CoquiTTS is None or playsound is None:
            return False
        if not self._ensure_coqui_engine():
            return False
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp_path = tmp.name
            kwargs: dict[str, object] = {}
            if self._settings.coqui_language:
                kwargs["language"] = self._settings.coqui_language
            speaker_wav = self._settings.coqui_speaker_wav
            if speaker_wav and os.path.exists(speaker_wav):
                kwargs["speaker_wav"] = speaker_wav
            self._coqui_engine.tts_to_file(text=text, file_path=tmp_path, **kwargs)
            playsound(tmp_path)
            return True
        except Exception:
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _speak_piper(self, text: str) -> bool:
        if playsound is None:
            return False
        piper_bin = self._resolve_piper_bin()
        model = self._settings.piper_model_path
        if not piper_bin or not model or not os.path.exists(model):
            return False
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp_path = tmp.name
            cmd = [
                piper_bin,
                "--model",
                model,
                "--output_file",
                tmp_path,
                "--speaker",
                str(self._settings.piper_speaker_id),
                "--length_scale",
                str(self._settings.piper_length_scale),
            ]
            subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            playsound(tmp_path)
            return True
        except Exception:
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _ensure_coqui_engine(self) -> bool:
        if self._coqui_engine is not None:
            return True
        if CoquiTTS is None:
            return False
        try:
            use_gpu = self._should_use_gpu()
            self._coqui_engine = CoquiTTS(
                model_name=self._settings.coqui_model,
                progress_bar=False,
                gpu=use_gpu,
            )
            return True
        except Exception:
            self._coqui_engine = None
            return False

    def _should_use_gpu(self) -> bool:
        if self._settings.coqui_device == "cpu":
            return False
        if self._settings.coqui_device == "cuda":
            return torch is not None and bool(getattr(torch.cuda, "is_available", lambda: False)())
        return torch is not None and bool(getattr(torch.cuda, "is_available", lambda: False)())

    def _can_use_coqui(self) -> bool:
        return CoquiTTS is not None and playsound is not None

    def _can_use_piper(self) -> bool:
        if playsound is None:
            return False
        piper_bin = self._resolve_piper_bin()
        return bool(piper_bin and self._settings.piper_model_path and os.path.exists(self._settings.piper_model_path))

    def _resolve_piper_bin(self) -> str:
        configured = self._settings.piper_bin.strip()
        if configured:
            if os.path.exists(configured):
                return configured
            detected = shutil.which(configured)
            return detected or ""
        detected = shutil.which("piper")
        return detected or ""

    def _should_suppress_repeat(self, text: str) -> bool:
        fingerprint = hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()
        now = time.time()
        if self._last_fingerprint == fingerprint and (
            now - self._last_spoken_ts
        ) < self._settings.repeat_window_seconds:
            return True
        return False

    def _remember(self, text: str) -> None:
        self._last_fingerprint = hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()
        self._last_spoken_ts = time.time()


class VoiceInput:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled and sr is not None
        self._recognizer = sr.Recognizer() if self._enabled else None

    @property
    def available(self) -> bool:
        return self._enabled

    def listen_yes_no(self, timeout_seconds: int = 4) -> bool | None:
        if not self._enabled or self._recognizer is None:
            return None
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                self._recognizer.dynamic_energy_threshold = True
                self._recognizer.pause_threshold = 0.7
                audio = self._recognizer.listen(source, timeout=timeout_seconds, phrase_time_limit=3)
            text = self._recognizer.recognize_google(audio).strip().lower()
        except Exception:
            return None
        return parse_yes_no_intent(text)

    def listen_text(self, timeout_seconds: int = 6, phrase_time_limit: int = 6) -> str | None:
        if not self._enabled or self._recognizer is None:
            return None
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.4)
                self._recognizer.dynamic_energy_threshold = True
                audio = self._recognizer.listen(
                    source, timeout=timeout_seconds, phrase_time_limit=phrase_time_limit
                )
            text = self._recognizer.recognize_google(audio).strip()
        except Exception:
            return None
        return text or None
