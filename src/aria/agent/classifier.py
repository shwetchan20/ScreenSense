from __future__ import annotations

import json

from aria.perception.vlm_client import VLMClient


class Classifier:
    def __init__(self, *, vlm: VLMClient) -> None:
        self._vlm = vlm

    async def classify(self, *, user_task: str, screen_context: dict) -> dict:
        prompt = (
            "Classify the request. Output JSON only with one field: type.\n"
            "Allowed values: screen_task, conversation, memory_query.\n"
            f"User task: {user_task}\n"
            f"Screen context: {json.dumps(screen_context)}"
        )
        return await self._vlm.generate_json(prompt)
