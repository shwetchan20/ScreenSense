from __future__ import annotations

import asyncio
import os
import tempfile


class Voice:
    def __init__(self, *, voice_name: str = "en-US-JennyNeural") -> None:
        self._voice_name = voice_name

    async def speak(self, text: str) -> None:
        if not text.strip() or os.environ.get("ARIA_DISABLE_VOICE", "0").strip().lower() in {"1", "true", "yes"}:
            return
        import edge_tts
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = tmp.name
        communicator = edge_tts.Communicate(text=text, voice=self._voice_name)
        await communicator.save(tmp_path)
        await asyncio.to_thread(playsound, tmp_path)
        os.remove(tmp_path)
