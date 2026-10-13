from __future__ import annotations

import json

from aria.perception.vlm_client import VLMClient


class Planner:
    def __init__(self, *, vlm: VLMClient) -> None:
        self._vlm = vlm

    async def plan(self, *, user_task: str, screen_context: dict, memory_context: list[dict]) -> dict:
        prompt = (
            "Create a step plan for this desktop task. Output JSON only: {\"steps\": [...]}\n"
            "Each step object must include: step, action, and either path/content, element_id, or text/key/amount.\n"
            "Supported actions: write_file (with path and content), create_dir (with path), click (with element_id or coords), type (with text), key (with key).\n"
            f"User task: {user_task}\n"
            f"Screen context: {json.dumps(screen_context)}\n"
            f"Recent context from memory: {json.dumps(memory_context)}"
        )
        return await self._vlm.generate_json(prompt)
