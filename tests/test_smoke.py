# tests/test_smoke.py
# Real smoke test - requires Ollama running with the configured ARIA vision model pulled
# Run with: pytest tests/test_smoke.py -v

import asyncio
import json

import httpx

from aria.config import VLM_MODEL
from aria.perception.screen_context import (
    get_uia_context,
    get_unified_screen_context,
    get_win32_context,
)
from aria.perception.vlm_client import query_vlm_text


def test_ollama_reachable() -> None:
    r = httpx.get("http://localhost:11434/api/tags")
    assert r.status_code == 200, "Ollama not running"
    models = [m["name"] for m in r.json().get("models", [])]
    assert any(m.startswith(VLM_MODEL) for m in models), f"{VLM_MODEL} not pulled. Models found: {models}"


def test_screen_context_returns_valid_json() -> None:
    context = asyncio.run(get_unified_screen_context())
    assert isinstance(context, dict), "Context must be a dict"
    assert "active_app" in context, "Missing active_app"
    assert "window_title" in context, "Missing window_title"
    assert "interactable_elements" in context, "Missing interactable_elements"
    assert "visible_text" in context, "Missing visible_text"
    assert isinstance(context["interactable_elements"], list), "interactable_elements must be list"


def test_vlm_text_query() -> None:
    response = asyncio.run(query_vlm_text('Output this exact JSON: {"status": "ok"}'))
    parsed = json.loads(response)
    assert parsed.get("status") == "ok", f"Unexpected response: {response}"


def test_uia_returns_tabs() -> None:
    result = get_uia_context()
    assert "browser_tabs" in result
    assert "uia_focused_element" in result


def test_win32_returns_active_app() -> None:
    result = get_win32_context()
    assert "active_app" in result
    assert "window_title" in result
    assert len(result["active_app"]) > 0

