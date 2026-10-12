import base64
import json
import os
import re

import httpx

from aria.config import (
    INFERENCE_BACKEND,
    LLAMA_MODEL,
    LLAMA_SERVER_URL,
    OLLAMA_URL,
    VLM_MODEL,
)


class VLMClient:
    def __init__(
        self,
        *,
        ollama_url: str | None = None,
        model: str | None = None,
        backend: str | None = None,
        llama_url: str | None = None,
    ) -> None:
        self._backend = (backend or INFERENCE_BACKEND).strip().lower()
        self._ollama_url = ollama_url or f"{OLLAMA_URL}/api/generate"
        self._llama_url = llama_url or LLAMA_SERVER_URL
        if model is not None:
            self._model = model
        else:
            self._model = LLAMA_MODEL if self._backend == "llama-server" else VLM_MODEL

    async def generate_json(
        self,
        prompt: str,
        image_bytes: bytes | None = None,
        format_spec: str | dict[str, object] = "json",
        num_predict: int = 384,
        timeout_seconds: float | None = None,
        num_ctx: int | None = None,
    ) -> dict:
        timeout_value = float(os.environ.get("ARIA_VLM_TIMEOUT_SECONDS", "30")) if timeout_seconds is None else timeout_seconds
        num_ctx_value = int(os.environ.get("ARIA_VLM_NUM_CTX", "2048")) if num_ctx is None else num_ctx
        max_retries = int(os.environ.get("ARIA_VLM_MAX_RETRIES", "2"))
        current_num_predict = num_predict

        last_error: Exception | None = None
        response_text = ""

        for attempt in range(max(1, max_retries)):
            try:
                if self._backend == "llama-server":
                    payload: dict[str, object] = {
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": current_num_predict,
                    }
                    if format_spec == "json":
                        payload["response_format"] = {"type": "json_object"}
                    url = self._llama_url
                else:
                    payload = {
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "think": False,
                        "format": format_spec,
                        "options": {"temperature": 0.0, "num_predict": current_num_predict, "num_ctx": num_ctx_value},
                    }
                    if image_bytes is not None:
                        payload["images"] = [base64.b64encode(image_bytes).decode("utf-8")]
                    url = self._ollama_url

                async with httpx.AsyncClient(timeout=timeout_value) as client:
                    response = await client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()

                if self._backend == "llama-server":
                    choices = body.get("choices", [])
                    if choices and isinstance(choices[0], dict):
                        response_text = str(choices[0].get("message", {}).get("content", "")).strip()
                    else:
                        response_text = ""
                else:
                    response_text = self._extract_response_text(body)

                cleaned = self._clean_json_text(response_text)
                return json.loads(cleaned)
            except Exception as exc:
                last_error = exc
                if isinstance(exc, json.JSONDecodeError):
                    current_num_predict = min(current_num_predict * 2, 1536)
                continue

        if last_error is not None:
            raise RuntimeError(
                f"Failed to parse JSON response from {self._backend} (model {self._model}): {response_text[:400]!r}"
            ) from last_error
        raise RuntimeError(f"Failed to get JSON response from {self._backend}")

    async def generate_text(
        self,
        prompt: str,
        image_bytes: bytes | None = None,
        num_predict: int = 384,
        timeout_seconds: float | None = None,
        num_ctx: int | None = None,
    ) -> str:
        timeout_value = float(os.environ.get("ARIA_VLM_TIMEOUT_SECONDS", "30")) if timeout_seconds is None else timeout_seconds
        num_ctx_value = int(os.environ.get("ARIA_VLM_NUM_CTX", "2048")) if num_ctx is None else num_ctx

        if self._backend == "llama-server":
            payload: dict[str, object] = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": num_predict,
            }
            url = self._llama_url
        else:
            payload = {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.0, "num_predict": num_predict, "num_ctx": num_ctx_value},
            }
            if image_bytes is not None:
                payload["images"] = [base64.b64encode(image_bytes).decode("utf-8")]
            url = self._ollama_url

        async with httpx.AsyncClient(timeout=timeout_value) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

        if self._backend == "llama-server":
            choices = body.get("choices", [])
            if choices and isinstance(choices[0], dict):
                return str(choices[0].get("message", {}).get("content", "")).strip()
            return ""
        return self._extract_response_text(body)

    @staticmethod
    def _clean_json_text(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```"):
                if lines[-1].strip() == "```":
                    stripped = "\n".join(lines[1:-1]).strip()
                else:
                    stripped = "\n".join(lines[1:]).strip()
        match = re.search(r"(\{.*\}|\[.*\])", stripped, re.DOTALL)
        if match:
            return match.group(1).strip()
        return stripped

    @staticmethod
    def _extract_response_text(body: dict[str, object]) -> str:
        response_text = str(body.get("response", "")).strip()
        if response_text:
            return response_text
        thinking_text = str(body.get("thinking", "")).strip()
        if thinking_text:
            return thinking_text
        return ""


async def query_vlm_text(prompt: str) -> str:
    client = VLMClient()
    return await client.generate_text(prompt, num_predict=64)

