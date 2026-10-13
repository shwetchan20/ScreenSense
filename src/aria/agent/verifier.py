from __future__ import annotations

import json

from aria.perception.vlm_client import VLMClient


class Verifier:
    def __init__(self, *, vlm: VLMClient) -> None:
        self._vlm = vlm

    async def verify(self, *, action_spec: dict, pre_context: dict, post_context: dict, post_image: bytes) -> dict:
        prompt = (
            "Did this action succeed? Output JSON only: {\"success\": true|false, \"observation\": \"...\"}.\n"
            f"Action: {json.dumps(action_spec)}\n"
            f"Before context: {json.dumps(pre_context)}\n"
            f"After context: {json.dumps(post_context)}"
        )
        return await self._vlm.generate_json(prompt, image_bytes=post_image)
