"""
ARIA Pipeline Integration Smoke Test
=====================================
Tests the full classifier + planner pipeline against the live llama-server
backend. Does NOT execute any pyautogui actions. All sandbox actions use the
research/test_workspace directory only.

Run:
    .venv\Scripts\python.exe research\test_pipeline_integration.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ── Environment setup (must precede aria imports) ────────────────────────────
os.environ.setdefault("ARIA_INFERENCE_BACKEND", "llama-server")
os.environ.setdefault("ARIA_LLAMA_SERVER_URL", "http://127.0.0.1:8081/v1/chat/completions")
os.environ.setdefault("ARIA_LLAMA_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m")
os.environ.setdefault("ARIA_VLM_TIMEOUT_SECONDS", "30")
os.environ.setdefault("ARIA_VLM_MAX_RETRIES", "2")
os.environ.setdefault("ARIA_VLM_NUM_CTX", "2048")
os.environ.setdefault("ARIA_PERCEPTION_MODE", "text_grounded")
os.environ.setdefault("ARIA_ENABLE_VERIFICATION", "0")  # baseline first

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aria.agent.classifier import Classifier  # noqa: E402
from aria.agent.planner import Planner  # noqa: E402
from aria.perception.vlm_client import VLMClient  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
results: list[dict] = []


def record(name: str, status: str, elapsed_ms: int, detail: str = "") -> None:
    icon = "PASS" if status == PASS else "FAIL"
    print(f"  [{icon}] {name} ({elapsed_ms}ms){': ' + detail if detail else ''}")
    results.append({"name": name, "status": status, "elapsed_ms": elapsed_ms, "detail": detail})


def summarize() -> None:
    passed = sum(1 for r in results if r["status"] == PASS)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        print("Failed tests:")
        for r in results:
            if r["status"] != PASS:
                print(f"  - {r['name']}: {r['detail']}")
    print("=" * 60)


# Minimal synthetic screen context for planner tests
SAMPLE_SCREEN_CTX = {
    "focused_window": "Windows Explorer",
    "current_view": "File manager showing the Desktop",
    "uia_elements": [
        {"id": 1, "name": "research/test_workspace", "type": "ListItem", "center": [400, 300]},
    ],
    "visible_text": ["research", "test_workspace"],
    "screen_state": "desktop",
    "page_summary": "Desktop file manager",
}


# ── Tests ────────────────────────────────────────────────────────────────────

async def test_backend_health(client: VLMClient) -> None:
    """Verify JSON round-trip to llama-server."""
    t0 = time.perf_counter()
    try:
        result = await client.generate_json(
            'Return ONLY this JSON, no extra text: {"ping": "pong"}',
            num_predict=32,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if isinstance(result, dict) and result.get("ping") == "pong":
            record("backend_health_json", PASS, elapsed_ms, f"got {result}")
        else:
            record("backend_health_json", FAIL, elapsed_ms, f"unexpected result: {result}")
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        record("backend_health_json", FAIL, elapsed_ms, str(exc))


async def test_classifier_screen_task(classifier: Classifier) -> None:
    """Classifier should label a screen task correctly."""
    t0 = time.perf_counter()
    try:
        ctx = json.dumps({"focused_window": "Desktop", "screen_state": "desktop"})
        result = await classifier.classify(
            user_task="Create a file called hello.txt in research/test_workspace",
            screen_context=ctx,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        task_type = result.get("type", "")
        if task_type == "screen_task":
            record("classifier_screen_task", PASS, elapsed_ms, f"type={task_type!r}")
        else:
            record("classifier_screen_task", FAIL, elapsed_ms, f"expected screen_task, got {task_type!r}; full={result}")
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        record("classifier_screen_task", FAIL, elapsed_ms, str(exc))


async def test_classifier_conversation(classifier: Classifier) -> None:
    """Classifier should label a conversational query correctly."""
    t0 = time.perf_counter()
    try:
        ctx = json.dumps({"focused_window": "Desktop", "screen_state": "desktop"})
        result = await classifier.classify(
            user_task="What is the capital of France?",
            screen_context=ctx,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        task_type = result.get("type", "")
        if task_type in ("conversation", "memory_query"):
            record("classifier_conversation", PASS, elapsed_ms, f"type={task_type!r}")
        else:
            record("classifier_conversation", FAIL, elapsed_ms, f"expected conversation, got {task_type!r}")
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        record("classifier_conversation", FAIL, elapsed_ms, str(exc))


async def test_planner_file_task(planner: Planner) -> None:
    """Planner should produce a valid steps list for a file creation task."""
    t0 = time.perf_counter()
    try:
        ctx = json.dumps(SAMPLE_SCREEN_CTX)
        result = await planner.plan(
            user_task="Create a file called hello.txt inside research/test_workspace with content 'hello world'",
            screen_context=ctx,
            memory_context=[],
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        steps = result.get("steps", [])
        if isinstance(steps, list) and len(steps) >= 1:
            record("planner_file_task", PASS, elapsed_ms, f"{len(steps)} steps returned")
        else:
            record("planner_file_task", FAIL, elapsed_ms, f"no steps: {result}")
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        record("planner_file_task", FAIL, elapsed_ms, str(exc))


async def test_planner_ambiguous_task(planner: Planner) -> None:
    """Planner should still return a parseable response for an underspecified task."""
    t0 = time.perf_counter()
    try:
        ctx = json.dumps(SAMPLE_SCREEN_CTX)
        result = await planner.plan(
            user_task="Do the thing",
            screen_context=ctx,
            memory_context=[],
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        # Accept any valid JSON response with a steps key (even empty list)
        if "steps" in result:
            record("planner_ambiguous_task", PASS, elapsed_ms, f"steps={result['steps']!r}")
        else:
            record("planner_ambiguous_task", FAIL, elapsed_ms, f"no steps key: {result}")
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        record("planner_ambiguous_task", FAIL, elapsed_ms, str(exc))


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("ARIA Pipeline Integration Test")
    print(f"  backend: {os.environ['ARIA_INFERENCE_BACKEND']}")
    print(f"  url:     {os.environ['ARIA_LLAMA_SERVER_URL']}")
    print(f"  model:   {os.environ['ARIA_LLAMA_MODEL']}")
    print("=" * 60)

    client = VLMClient()
    classifier = Classifier(vlm=client)
    planner = Planner(vlm=client)

    print("\n[1/5] Backend health")
    await test_backend_health(client)

    print("\n[2/5] Classifier: screen task")
    await test_classifier_screen_task(classifier)

    print("\n[3/5] Classifier: conversation")
    await test_classifier_conversation(classifier)

    print("\n[4/5] Planner: file creation task")
    await test_planner_file_task(planner)

    print("\n[5/5] Planner: ambiguous task")
    await test_planner_ambiguous_task(planner)

    summarize()
    sys.exit(0 if all(r["status"] == PASS for r in results) else 1)


asyncio.run(main())
