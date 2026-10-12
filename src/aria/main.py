from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

import httpx
from dotenv import load_dotenv
from typing import Any

from aria.agent.action_runner import ActionRunner
from aria.agent.classifier import Classifier
from aria.agent.coding_helper import CodingHelper
from aria.agent.executor import Executor
from aria.agent.planner import Planner
from aria.agent.reflector import Reflector
from aria.agent.verifier import Verifier
from aria.config import (
    ENABLE_VERIFICATION,
    INFERENCE_BACKEND,
    LLAMA_SERVER_URL,
    OLLAMA_URL,
    SQLITE_PATH,
    TELEGRAM_BOT_TOKEN,
    VLM_MODEL,
)
from aria.interface.telegram_bot import TelegramInterface
from aria.interface.voice import Voice
from aria.memory.sqlite_store import SQLiteStore
from aria.perception.screen_context import ScreenContextCollector
from aria.perception.vlm_client import VLMClient


class AriaRuntime:
    def __init__(self) -> None:
        load_dotenv(override=True)
        self._verification_enabled = os.environ.get("ARIA_ENABLE_VERIFICATION", str(int(ENABLE_VERIFICATION))).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        telegram_disabled = os.environ.get("ARIA_DISABLE_TELEGRAM", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        token = (
            os.environ.get("ARIA_TELEGRAM_TOKEN", "").strip()
            or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        )
        chat_id = (
            os.environ.get("ARIA_TELEGRAM_CHAT_ID", "").strip()
            or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        )
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)
        # VLMClient reads ARIA_INFERENCE_BACKEND from env/config automatically;
        # only pass ollama_url/model when explicitly using Ollama backend to avoid
        # overriding the llama-server config when ARIA_INFERENCE_BACKEND=llama-server.
        if INFERENCE_BACKEND.strip().lower() == "llama-server":
            self._vlm = VLMClient()
        else:
            self._vlm = VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
        self._screen = ScreenContextCollector(vlm=self._vlm)
        self._memory = SQLiteStore(SQLITE_PATH)
        self._classifier = Classifier(vlm=self._vlm)
        self._coding_helper = CodingHelper()
        self._planner = Planner(vlm=self._vlm)
        self._executor = Executor()
        self._runner = ActionRunner()
        self._verifier = Verifier(vlm=self._vlm)
        self._reflector = Reflector(vlm=self._vlm)
        self._voice = Voice(voice_name="en-US-JennyNeural")
        from aria.perception.trigger import TriggerSystem

        self._trigger = TriggerSystem(queue=self._queue)
        self._started_at = time.time()
        self._last_task = ""
        self._last_outcome = "idle"
        self._telegram: TelegramInterface | None = None
        if token and chat_id and not telegram_disabled:
            self._telegram = TelegramInterface(
                token=token,
                chat_id=chat_id,
                on_user_message=self._on_telegram_message,
                on_status=self._on_status_command,
                on_health=self._on_health_command,
                on_goal=self._on_goal_command,
            )

    async def run(self) -> None:
        if self._telegram is not None:
            await self._telegram.start()
        await self._trigger.start()
        worker = asyncio.create_task(self._pipeline_worker())
        await worker

    async def run_observe(self, *, interval_seconds: float, max_cycles: int) -> None:
        cycles = 0
        while True:
            context = await self._screen.get_unified_screen_context()
            report = self._render_context_report(context)
            print(f"[OBSERVE]\n{report}\n")
            cycles += 1
            if max_cycles > 0 and cycles >= max_cycles:
                return
            await asyncio.sleep(interval_seconds)

    async def _on_telegram_message(self, text: str) -> str:
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        await self._trigger.enqueue("telegram", user_task=text, future=future)
        return await future

    async def _on_status_command(self) -> str:
        uptime_seconds = int(time.time() - self._started_at)
        goal = self._memory.get_goal(date_key=time.strftime("%Y-%m-%d", time.localtime()))
        return (
            f"ARIA local runtime online. "
            f"Uptime: {uptime_seconds}s. "
            f"Queue: {self._queue.qsize()}. "
            f"Last task: {self._last_task or 'none'}. "
            f"Last outcome: {self._last_outcome}. "
            f"Goal: {goal or 'none'}."
        )

    async def _on_health_command(self) -> str:
        if INFERENCE_BACKEND.strip().lower() == "llama-server":
            health_url = LLAMA_SERVER_URL.replace("/v1/chat/completions", "/health")
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(health_url)
            response.raise_for_status()
            data = response.json()
            status = data.get("status", "unknown")
            if status != "ok":
                raise RuntimeError(f"Health check failed: llama-server status={status!r}")
            return f"Health OK: llama-server reachable at {health_url}, status={status!r}."
        else:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [str(m.get("name", "")) for m in data.get("models", [])]
            has_vlm = any(name.startswith(VLM_MODEL) for name in models)
            if not has_vlm:
                raise RuntimeError(f"Health check failed: {VLM_MODEL} missing")
            return f"Health OK: ollama reachable, {VLM_MODEL} available."

    async def _on_goal_command(self, goal_text: str) -> str:
        date_key = time.strftime("%Y-%m-%d", time.localtime())
        if not goal_text:
            current = self._memory.get_goal(date_key=date_key)
            return f"Current goal: {current or 'none'}"
        self._memory.set_goal(date_key=date_key, goal_text=goal_text)
        return f"Goal updated: {goal_text}"

    async def _pipeline_worker(self) -> None:
        while True:
            event = await self._queue.get()
            result = await self._handle_event(event)
            if event.response_future is not None and not event.response_future.done():
                event.response_future.set_result(result)
            self._queue.task_done()

    async def _handle_event(self, event: Any) -> str:
        screen_context = await self._screen.get_unified_screen_context()
        coding_analysis = self._coding_helper.analyze(screen_context=screen_context)
        screen_context["coding_analysis"] = coding_analysis
        user_task = event.user_task.strip()

        if not user_task:
            self._last_outcome = "context_updated"
            print(f"[PIPELINE] {self._summarize_context(screen_context)}")
            return "Activity observed. Context updated."

        self._last_task = user_task
        self._memory.save_screen_snapshot(task_text=user_task, context=screen_context)

        classification = await self._classifier.classify(
            user_task=user_task,
            screen_context=self._reasoning_context(screen_context),
        )
        task_type = str(classification["type"])

        if task_type == "conversation":
            response = await self._handle_conversation(user_task, screen_context)
            await self._voice.speak(response)
            self._last_outcome = "conversation"
            return response

        if task_type == "memory_query":
            response = await self._handle_memory_query(user_task)
            await self._voice.speak(response)
            self._last_outcome = "memory_query"
            return response

        response = await self._run_screen_task(user_task, screen_context)
        await self._voice.speak(response)
        self._last_outcome = "screen_task_done"
        return response

    async def _handle_conversation(self, user_task: str, screen_context: dict) -> str:
        prompt = (
            "Respond conversationally in under 3 sentences. Output JSON with field response.\n"
            f"User: {user_task}\n"
            f"Context: {json.dumps(self._reasoning_context(screen_context))}"
        )
        body = await self._vlm.generate_json(prompt)
        return str(body["response"])

    async def _handle_memory_query(self, user_task: str) -> str:
        recent = self._memory.recent_task_context(limit=5)
        prompt = (
            "Answer the memory query using the provided history. Output JSON with field response.\n"
            f"Query: {user_task}\n"
            f"History: {json.dumps(recent)}"
        )
        body = await self._vlm.generate_json(prompt)
        return str(body["response"])

    async def _run_screen_task(self, user_task: str, screen_context: dict) -> str:
        memory_context = self._memory.recent_task_context(limit=5)
        plan = await self._planner.plan(
            user_task=user_task,
            screen_context=self._reasoning_context(screen_context),
            memory_context=memory_context,
        )

        steps = list(plan.get("steps", []))
        if not steps:
            self._memory.save_task_record(task_text=user_task, plan=plan, status="done")
            return "No action needed."

        current_context = screen_context
        for step in steps:
            action_spec = self._executor.build_action_spec(step=step, screen_context=current_context)
            await asyncio.to_thread(self._runner.run, action_spec)

            if not self._verification_enabled:
                current_context = await self._screen.get_unified_screen_context()
                continue

            post_image, _ = await self._screen.capture_screenshot()
            post_context = await self._screen.get_unified_screen_context()
            verification = await self._verifier.verify(
                action_spec=action_spec,
                pre_context=self._reasoning_context(current_context),
                post_context=self._reasoning_context(post_context),
                post_image=post_image,
            )

            reflection = await self._reflector.reflect(
                user_task=user_task,
                plan=plan,
                step=step,
                verification=verification,
                screen_context=post_context,
            )
            decision = str(reflection.get("decision", "next_step"))

            if decision == "next_step":
                current_context = post_context
                continue
            if decision == "done":
                self._memory.save_task_record(task_text=user_task, plan=plan, status="done")
                return f"Task complete: {user_task}"
            if decision == "replan":
                new_plan = await self._planner.plan(
                    user_task=user_task,
                    screen_context=self._reasoning_context(post_context),
                    memory_context=self._memory.recent_task_context(limit=5),
                )
                self._memory.save_task_record(task_text=user_task, plan=new_plan, status="replan")
                self._last_outcome = "replan"
                return "Replanned due to screen changes."
            if decision == "abort":
                self._memory.save_task_record(task_text=user_task, plan=plan, status="abort")
                self._last_outcome = "abort"
                raise RuntimeError(f"Task aborted by reflector: {user_task}")

        self._memory.save_task_record(task_text=user_task, plan=plan, status="done")
        return f"Task complete: {user_task}"

    @staticmethod
    def _summarize_context(context: dict) -> str:
        app = str(context.get("active_app", ""))
        title = str(context.get("window_title", ""))
        state = str(context.get("screen_state", ""))
        text_count = len(context.get("visible_text", []))
        elem_count = len(context.get("interactable_elements", []))
        return (
            f"app={app} title={title!r} state={state} "
            f"visible_text={text_count} interactable_elements={elem_count}"
        )

    @staticmethod
    def _reasoning_context(context: dict) -> dict:
        actionable = context.get("actionable_context", {})
        return {
            "active_app": context.get("active_app", ""),
            "window_title": context.get("window_title", ""),
            "screen_state": context.get("screen_state", ""),
            "focused_window_summary": context.get("focused_window_summary", ""),
            "current_task_summary": context.get("current_task_summary", ""),
            "browser_address_summary": context.get("browser_address_summary", ""),
            "browser_page_text_summary": context.get("browser_page_text_summary", []),
            "window_visible_text_summary": context.get("window_visible_text_summary", []),
            "visible_content_summary": context.get("visible_content_summary", ""),
            "current_content": context.get("current_content", ""),
            "detailed_description": context.get("detailed_description", ""),
            "browser_tabs_summary": context.get("browser_tabs_summary", []),
            "other_running_apps_summary": context.get("other_running_apps_summary", []),
            "visible_text": context.get("visible_text", []),
            "uia_focused_element": actionable.get("uia_focused_element", context.get("uia_focused_element", "")),
            "interactable_elements": actionable.get("interactable_elements", context.get("interactable_elements", [])),
            "coding_analysis": context.get("coding_analysis", {}),
        }

    @staticmethod
    def _render_context_report(context: dict) -> str:
        focused_window_summary = str(context.get("focused_window_summary", "")).strip()
        current_task_summary = str(context.get("current_task_summary", "")).strip()
        detailed_description = str(context.get("detailed_description", "")).strip()
        visible_content_summary = str(context.get("visible_content_summary", "")).strip()
        browser_tabs_summary = list(context.get("browser_tabs_summary", []))
        browser_address_summary = str(context.get("browser_address_summary", "")).strip()
        browser_page_text_summary = list(context.get("browser_page_text_summary", []))
        window_visible_text_summary = list(context.get("window_visible_text_summary", []))
        other_running_apps_summary = list(context.get("other_running_apps_summary", []))
        final_user_state_summary = str(context.get("final_user_state_summary", "")).strip()
        coding_analysis = dict(context.get("coding_analysis", {}))

        lines: list[str] = []
        lines.append("Here's what's currently on your screen:")
        lines.append("")
        if focused_window_summary:
            lines.append(f"Focused Window: {focused_window_summary}")
        if current_task_summary:
            lines.append(f"Current View: {current_task_summary}")
        if visible_content_summary:
            lines.append(f"Visible Content: {visible_content_summary}")
        elif detailed_description:
            lines.append(f"Visible Content: {detailed_description}")
        if browser_address_summary:
            lines.append(f"Address/Search: {browser_address_summary}")
        if browser_page_text_summary:
            lines.append("Visible Page Text:")
            for item in browser_page_text_summary[:5]:
                lines.append(f"  - {item}")
        if window_visible_text_summary:
            lines.append("Window Text:")
            for item in window_visible_text_summary[:6]:
                lines.append(f"  - {item}")
        if browser_tabs_summary:
            lines.append("Browser Tabs:")
            for title in browser_tabs_summary:
                lines.append(f"  - {title}")
        if other_running_apps_summary:
            lines.append("Other Running Apps:")
            for app_name in other_running_apps_summary:
                lines.append(f"  - {app_name}")
        if coding_analysis.get("has_error"):
            lines.append("Coding Diagnosis:")
            exception_name = str(coding_analysis.get("primary_exception", "")).strip()
            if exception_name:
                lines.append(f"  - Exception: {exception_name}")
            primary_file = str(coding_analysis.get("primary_file", "")).strip()
            primary_line = int(coding_analysis.get("primary_line", 0) or 0)
            if primary_file and primary_line:
                lines.append(f"  - Location: {primary_file}:{primary_line}")
            diagnosis = str(coding_analysis.get("diagnosis", "")).strip()
            if diagnosis:
                lines.append(f"  - Diagnosis: {diagnosis}")
            suggestion = str(coding_analysis.get("suggestion", "")).strip()
            if suggestion:
                lines.append(f"  - Suggested Fix: {suggestion}")
        if final_user_state_summary:
            lines.append("")
            lines.append(final_user_state_summary)
        return "\n".join(lines)


    async def run_task(self, user_task: str) -> str:
        from aria.perception.trigger import TriggerEvent

        event = TriggerEvent(source="direct_cli", user_task=user_task, created_at=time.time())
        return await self._handle_event(event)


async def main() -> None:
    runtime = AriaRuntime()
    await runtime.run()


def run_cli() -> None:
    parser = argparse.ArgumentParser(prog="python -m aria.main")
    parser.add_argument("--observe", action="store_true", help="Run screenshot->VLM context loop without Telegram")
    parser.add_argument("--observe-interval", type=float, default=3.0, help="Seconds between observe cycles")
    parser.add_argument("--observe-cycles", type=int, default=0, help="Stop after N cycles (0 = infinite)")
    parser.add_argument("--task", type=str, default="", help="Run a single task string directly")
    args = parser.parse_args()
    if args.task:
        runtime = AriaRuntime()
        result = asyncio.run(runtime.run_task(args.task))
        print(f"[RESULT] {result}")
        return
    if args.observe:
        runtime = AriaRuntime()
        asyncio.run(
            runtime.run_observe(
                interval_seconds=max(0.5, float(args.observe_interval)),
                max_cycles=max(0, int(args.observe_cycles)),
            )
        )
        return
    asyncio.run(main())


if __name__ == "__main__":
    run_cli()
