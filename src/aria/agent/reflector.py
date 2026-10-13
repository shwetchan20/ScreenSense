from __future__ import annotations

import json

from aria.perception.vlm_client import VLMClient


class Reflector:
    def __init__(self, *, vlm: VLMClient) -> None:
        self._vlm = vlm

    async def reflect(self, *, user_task: str, plan: dict, step: dict, verification: dict, screen_context: dict) -> dict:
        prompt = (
            "Return JSON only with decision field. Allowed: next_step, replan, done, abort.\n"
            f"Task: {user_task}\n"
            f"Plan: {json.dumps(plan)}\n"
            f"Current step: {json.dumps(step)}\n"
            f"Verification: {json.dumps(verification)}\n"
            f"Screen context: {json.dumps(screen_context)}"
        )
        return await self._vlm.generate_json(prompt)
