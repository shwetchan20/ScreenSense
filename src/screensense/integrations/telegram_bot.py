from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable
import uuid

import requests

from screensense.config import Settings
from screensense.core.response_cleaner import clean_response, clean_response_proactive
from screensense.core.ui_context import UiContextExtractor, UiContextSettings
from screensense.core.window_context import get_active_window_context
from screensense.core.capture import ScreenCapturer
from screensense.core.action_gate import ActionGate
from screensense.memory.sqlite_store import SQLiteMemoryStore
from screensense.perception.ui_context import UiAutomationContext
from screensense.inference.local_qwen import LocalQwenInferenceClient
from screensense.skills.code_ops import CodeOps
from screensense.skills.browser_ops import BrowserOps
from screensense.skills.file_ops import FileOps
from screensense.skills.system_ops import SystemOps

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.error import InvalidToken
    from telegram.ext import (
        Application,
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except Exception:  # pragma: no cover
    Application = None  # type: ignore[assignment]
    InvalidToken = None  # type: ignore[assignment]


@dataclass(slots=True)
class PendingAction:
    action_fn: Callable[[], str] | None
    reasoning: str


@dataclass(slots=True)
class PendingApproval:
    event: threading.Event
    result: bool | None


class ARIATelegramBot:
    def __init__(
        self,
        *,
        settings: Settings,
        memory_db: SQLiteMemoryStore,
        ui_context_provider: UiAutomationContext | None = None,
        ui_context_extractor: UiContextExtractor | None = None,
    ) -> None:
        self._settings = settings
        self._memory_db = memory_db
        self._token = settings.telegram_bot_token.strip()
        self._chat_id = settings.telegram_chat_id.strip()
        self._ui_context_provider = ui_context_provider or UiAutomationContext()
        self._ui_context_extractor = ui_context_extractor or UiContextExtractor(
            UiContextSettings(
                enabled=settings.enable_ocr_context,
                provider=settings.ocr_provider,
                min_interval_seconds=settings.ocr_min_interval_seconds,
                max_text_chars=settings.ocr_max_text_chars,
            )
        )
        self._capture_local = threading.local()
        self._app: Application | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pending_action = PendingAction(action_fn=None, reasoning="")
        self._last_error: str = ""
        self._last_error_ts: float = 0.0
        self._approvals_lock = threading.Lock()
        self._pending_approvals: dict[str, PendingApproval] = {}
        self._goal_callback: Callable[[str], str | None] | None = None
        self._health_callback: Callable[[], str] | None = None
        self._killlocal_callback: Callable[[], str] | None = None
        
        # Initialize LocalQwenInferenceClient with verified perception
        self._inference_client = LocalQwenInferenceClient(
            provider=settings.local_llm_provider,
            model=settings.local_llm_model,
            base_url=settings.local_llm_base_url,
            timeout_seconds=settings.local_llm_timeout_seconds,
            use_vision=False,  # Telegram doesn't need vision
            ui_context_extractor=self._ui_context_extractor,
            enable_verified_perception=settings.enable_verified_perception,
        )
        
        skill_allowlist = {
            "read_file",
            "list_directory",
            "find_files",
            "git_status",
            "get_syntax_errors",
            "search_web",
            "open_url",
            "search_docs",
            "search_stackoverflow",
            "copy_to_clipboard",
            "show_notification",
        }
        self._action_gate = ActionGate(
            allowlist=list(settings.action_allowlist) + sorted(skill_allowlist),
            telegram_request_approval=self.request_approval,
            whisper_callback=None,
            log_callback=None,
        )
        self._code_ops = CodeOps(self._action_gate)
        self._browser_ops = BrowserOps(self._action_gate)
        self._file_ops = FileOps(approval_callback=self._approve_file_write)
        self._system_ops = SystemOps(self._action_gate)
        print("[TG] skills loaded:", self._browser_ops, self._file_ops, self._code_ops)

    def start(self) -> bool:
        if Application is None:
            return False
        if not self._token or not self._chat_id:
            return False
        if not self._looks_like_token(self._token):
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ARIA-Telegram",
        )
        self._thread.start()
        return True

    def send_message(self, text: str) -> None:
        if not self._loop or not self._app:
            return
        cleaned = clean_response_proactive(text)
        if not cleaned:
            return
        asyncio.run_coroutine_threadsafe(
            self._app.bot.send_message(chat_id=self._chat_id, text=cleaned),
            self._loop,
        )

    def stop(self) -> None:
        if not self._loop or not self._app:
            return
        asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop)

    def send_proactive_alert(
        self,
        *,
        message: str,
        reasoning: str,
        action_fn: Callable[[], str] | None = None,
    ) -> None:
        if not self._loop or not self._app:
            return
        cleaned = clean_response_proactive(message)
        if not cleaned:
            return
        self._pending_action = PendingAction(action_fn=action_fn, reasoning=reasoning or "")
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✓ Do it", callback_data="action_do"),
                    InlineKeyboardButton("✕ Skip", callback_data="action_skip"),
                    InlineKeyboardButton("? More info", callback_data="action_more"),
                ]
            ]
        )
        asyncio.run_coroutine_threadsafe(
            self._app.bot.send_message(
                chat_id=self._chat_id,
                text=cleaned,
                reply_markup=markup,
            ),
            self._loop,
        )

    def request_approval(self, preview: str, timeout_seconds: float) -> bool | None:
        if not self._loop or not self._app:
            return None
        request_id = uuid.uuid4().hex[:10]
        event = threading.Event()
        with self._approvals_lock:
            self._pending_approvals[request_id] = PendingApproval(event=event, result=None)
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✓ Yes", callback_data=f"approve:{request_id}:yes"),
                    InlineKeyboardButton("✕ No", callback_data=f"approve:{request_id}:no"),
                ]
            ]
        )
        asyncio.run_coroutine_threadsafe(
            self._app.bot.send_message(
                chat_id=self._chat_id,
                text=preview,
                reply_markup=markup,
            ),
            self._loop,
        )
        event.wait(timeout_seconds)
        with self._approvals_lock:
            pending = self._pending_approvals.pop(request_id, None)
        if pending is None:
            return None
        return pending.result

    def _run(self) -> None:
        if Application is None:
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._app = ApplicationBuilder().token(self._token).build()
        self._register_handlers(self._app)
        try:
            loop.run_until_complete(self._startup_async())
            loop.run_forever()
        except Exception:
            return

    async def _startup_async(self) -> None:
        if self._app is None:
            return
        try:
            await self._app.initialize()
            await self._app.start()
            if self._app.updater is not None:
                await self._app.updater.start_polling()
            try:
                await self._send_startup_message()
            except Exception:
                pass
        except Exception:
            await self._shutdown_async()

    async def _shutdown_async(self) -> None:
        if self._app is None:
            return
        try:
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        finally:
            if self._loop is not None:
                self._loop.stop()

    def _register_handlers(self, app: Application) -> None:
        app.add_handler(CommandHandler("status", self._on_status))
        app.add_handler(CommandHandler("killlocal", self._on_killlocal))
        app.add_handler(CommandHandler("health", self._on_health))
        app.add_handler(CommandHandler("focus", self._on_focus))
        app.add_handler(CommandHandler("resume", self._on_resume))
        app.add_handler(CommandHandler("goal", self._on_goal))
        app.add_handler(CommandHandler("clear", self._on_clear))
        app.add_handler(CallbackQueryHandler(self._on_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

    async def _send_startup_message(self) -> None:
        if self._app is None:
            return
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        days_left = self._days_to_deadline(now)
        if days_left is None:
            deadline_text = "deadline not set."
        else:
            deadline_text = f"{days_left} days to deadline."
        text = f"ARIA online. {time_str}. {deadline_text}"
        try:
            await self._app.bot.send_message(chat_id=self._chat_id, text=text)
        except Exception as exc:
            self._record_error(f"startup_message_failed: {exc}")

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.message.text is None:
            return
        user_text = update.message.text.strip()
        print(f"[TG] received: {user_text}")
        if not user_text:
            return
        try:
            goal_response = None
            if hasattr(self, "_goal_callback") and self._goal_callback is not None:
                goal_response = self._goal_callback(user_text)
            if goal_response:
                await update.message.reply_text(goal_response)
                self._memory_db.add_telegram_message(role="user", content=user_text)
                self._memory_db.add_telegram_message(role="assistant", content=goal_response)
                return
            message_lower = user_text.lower()
            try:
                ui_context = await self._capture_ui_context_async()
                print(f"[TG] ui_context: {ui_context}")
            except Exception as exc:
                print(f"[TG] ui_context FAILED: {exc}")
                ui_context = {}

            # ---- Tier 1: Read-only intents (no LLM) ----
            handled = await self._handle_tier1_intents(
                update=update,
                user_text=user_text,
                message_lower=message_lower,
                ui_context=ui_context,
            )
            if handled:
                return

            if any(w in message_lower for w in ["search", "find", "look up", "google"]):
                print("[TG] → intent: SEARCH")
                try:
                    results = await asyncio.to_thread(self._browser_ops.search_web_api, user_text)
                    print(f"[TG] search results: {results[:200]}")
                except Exception as exc:
                    print(f"[TG] search FAILED: {exc}")
                    results = ""
                if not results:
                    response = "search returned nothing"
                    await update.message.reply_text(response)
                    self._store_exchange(user_text, response)
                    return
                response = self._summarise_search_results(user_text=user_text, results=results)
                response = clean_response(response)
                print(f"[TG] → sending (search): {response[:120]}")
                await update.message.reply_text(response)
                self._store_exchange(user_text, response)
                return

            potential_url = _extract_url(user_text or "")
            if (
                potential_url
                and (
                    any(w in message_lower for w in ["open", "visit", "go to", "browse"])
                    or "http" in message_lower
                )
            ):
                print("[TG] → intent: OPEN_URL")
                url = potential_url
                print(f"[TG] extracted url: {url}")
                if not url:
                    response = "what URL should I open?"
                    await update.message.reply_text(response)
                    self._store_exchange(user_text, response)
                    return
                print(f"[TG] opening URL: {url}")
                try:
                    content = await self._browser_ops.open_url_async(url)
                    print(f"[TG] page content: {len(content)} chars")
                except Exception as exc:
                    print(f"[TG] open_url FAILED: {exc}")
                    content = ""
                if not content:
                    response = f"opened {url} but could not read content"
                    await update.message.reply_text(response)
                    self._store_exchange(user_text, response)
                    return
                response = self._summarise_page(url=url, content=content)
                response = clean_response(response)
                print(f"[TG] → sending (page): {response[:120]}")
                await update.message.reply_text(response)
                self._store_exchange(user_text, response)
                return

            if any(
                w in message_lower
                for w in ["files", "folder", "directory", "project", "what is in"]
            ):
                print("[TG] → intent: FILES")
                try:
                    files = self._file_ops.list_directory(".")
                    print(f"[TG] files: {files}")
                    file_list = ", ".join(files[:20])
                except Exception as exc:
                    print(f"[TG] file list FAILED: {exc}")
                    file_list = ""
                if not file_list:
                    response = "could not read directory"
                    await update.message.reply_text(response)
                    self._store_exchange(user_text, response)
                    return
                response = f"project has: {file_list}"
                response = clean_response(response)
                await update.message.reply_text(response)
                self._store_exchange(user_text, response)
                return

            if any(
                w in message_lower
                for w in ["working on", "screen", "see", "what is open", "current"]
            ):
                print("[TG] → intent: SCREEN")
                if not ui_context:
                    response = "cannot read screen right now"
                    await update.message.reply_text(response)
                    self._store_exchange(user_text, response)
                    return
                history = self._memory_db.recent_telegram_messages(limit=5)
                session_goal = self._get_today_goal()
                prompt = self._build_chat_prompt(
                    user_text=user_text,
                    ui_context=ui_context,
                    session_goal=session_goal,
                    history=history,
                )
                response = self._generate_response(prompt)
                response = clean_response(response)
                await update.message.reply_text(response)
                self._store_exchange(user_text, response)
                return

            print("[TG] -> intent: CHAT")
            history = self._memory_db.recent_telegram_messages(limit=5)
            session_goal = self._get_today_goal()
            prompt = self._build_chat_prompt(
                user_text=user_text,
                ui_context=ui_context,
                session_goal=session_goal,
                history=history,
            )
            response = self._generate_response(prompt)
            response = clean_response(response)
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
        except Exception as exc:
            import traceback

            self._record_error(f"message_handler_failed: {exc}")
            print("[Telegram] FULL ERROR:")
            traceback.print_exc()
            try:
                await update.message.reply_text(f"failed: {type(exc).__name__}: {exc}")
            except Exception:
                pass

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.callback_query is None:
            return
        query = update.callback_query
        await query.answer()
        data = (query.data or "").strip()
        if data.startswith("approve:"):
            parts = data.split(":")
            if len(parts) == 3:
                request_id = parts[1]
                decision = parts[2].lower() == "yes"
                with self._approvals_lock:
                    pending = self._pending_approvals.get(request_id)
                if pending is not None:
                    pending.result = decision
                    pending.event.set()
                    await query.message.reply_text("ok" if not decision else "done.")
            return
        if data == "action_do":
            result = self._execute_pending_action()
            await query.message.reply_text(result)
        elif data == "action_skip":
            self._log_skip()
            await query.message.reply_text("ok")
        elif data == "action_more":
            reasoning = self._pending_action.reasoning.strip() or "No additional details."
            await query.message.reply_text(reasoning)

    async def _on_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        summary = self._build_status_summary()
        health = self._health_callback() if self._health_callback is not None else ""
        text = f"{summary}\n{health}".strip()
        await update.message.reply_text(text)

    async def _on_killlocal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if self._killlocal_callback is None:
            await update.message.reply_text("local model not configured.")
            return
        response = self._killlocal_callback()
        await update.message.reply_text(response)

    async def _on_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        status = "running" if self._thread and self._thread.is_alive() else "stopped"
        if self._last_error:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._last_error_ts))
            text = f"telegram {status}. last_error {ts}: {self._last_error}"
        else:
            text = f"telegram {status}. no errors recorded."
        await update.message.reply_text(text)

    async def _on_focus(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        self._settings.focus_mode = True
        await update.message.reply_text("quiet mode on.")

    async def _on_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        self._settings.focus_mode = False
        recent = self._memory_db.recent_interactions(limit=3)
        if recent:
            summary = "; ".join(recent)
            text = f"back. anything happen? recent: {summary}"
        else:
            text = "back. anything happen? nothing logged yet."
        await update.message.reply_text(text)

    async def _on_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        text = (update.message.text or "").strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("got it.")
            return
        goal_text = parts[1].strip()
        if goal_text:
            self._memory_db.set_today_goal(self._today_key(), goal_text)
        await update.message.reply_text("got it.")

    async def _on_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        self._memory_db.clear_telegram_history()
        await update.message.reply_text("memory cleared.")

    async def _capture_ui_context_async(self) -> dict[str, object]:
        result = await asyncio.to_thread(self._ui_context_provider.capture)
        return result.context

    async def _handle_tier1_intents(
        self,
        *,
        update: Update,
        user_text: str,
        message_lower: str,
        ui_context: dict[str, object],
    ) -> bool:
        """Handle read-only, safe intents without using the LLM."""
        if update.message is None:
            return False

        # "what am i working on" / "what am I doing"
        if any(
            phrase in message_lower
            for phrase in ("what am i working on", "what am i doing", "current work")
        ):
            response = self._intent_working_on(ui_context)
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        # "any errors on screen"
        if "any errors" in message_lower or "errors on screen" in message_lower:
            response = self._intent_errors(ui_context)
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        # "how long have i been working"
        if "how long have i been working" in message_lower or "session time" in message_lower:
            response = self._intent_session_time()
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        # "how's my pc" / "how is my pc" / "pc health"
        if any(
            phrase in message_lower
            for phrase in ("how's my pc", "how is my pc", "pc health", "system health")
        ):
            response = self._intent_pc_health()
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        # "what did i do today"
        if "what did i do today" in message_lower or "what i did today" in message_lower:
            response = self._intent_today_summary()
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        # "git status"
        if "git status" in message_lower:
            response = self._intent_git_status()
            await update.message.reply_text(response or "git status empty.")
            self._store_exchange(user_text, response or "git status empty.")
            return True

        # "show my todos" / "todos"
        if "show my todos" in message_lower or "todos" == message_lower.strip():
            response = self._intent_todos()
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        # "what's open" / "whats open"
        if "what's open" in message_lower or "whats open" in message_lower:
            response = self._intent_whats_open()
            await update.message.reply_text(response)
            self._store_exchange(user_text, response)
            return True

        return False

    def _intent_working_on(self, ui_context: dict[str, object]) -> str:
        app = str(ui_context.get("active_app") or ui_context.get("process_name") or "unknown")
        file = str(ui_context.get("current_file") or "no file")
        project = str(ui_context.get("project") or "screensense")
        title = str(ui_context.get("window_title") or "").strip()
        parts = []
        parts.append(f"{file} in {project}")
        parts.append(f"{app} active")
        if title:
            parts.append(f'"{title}"')
        return ", ".join(parts)

    def _intent_errors(self, ui_context: dict[str, object]) -> str:
        text = self._extract_error_text(ui_context)
        if text:
            snippet = re.sub(r"\s+", " ", text).strip()
            if len(snippet) > 160:
                snippet = snippet[:157].rstrip() + "..."
            return f"errors detected: {snippet}"
        # fall back to raw fields
        errors = str(ui_context.get("error_list") or "").strip()
        terminal = str(
            ui_context.get("terminal_last_output")
            or ui_context.get("last_output")
            or ui_context.get("terminal_output")
            or ""
        ).strip()
        if errors:
            snippet = re.sub(r"\s+", " ", errors)
            return f"errors listed: {snippet[:160]}"
        if terminal and any(tok in terminal.lower() for tok in ("error", "exception", "failed", "traceback")):
            snippet = re.sub(r"\s+", " ", terminal)
            return f"terminal shows errors: {snippet[:160]}"
        return "no errors detected on screen."

    def _intent_session_time(self) -> str:
        raw = ""
        try:
            raw = self._memory_db.get_meta("session_start_ts")
            start_ts = float(raw) if raw else time.time()
        except Exception:
            start_ts = time.time()
        minutes = int((time.time() - start_ts) // 60)
        if minutes <= 0:
            return "session just started."
        hours = minutes // 60
        rem = minutes % 60
        if hours:
            return f"roughly {hours}h {rem}m this session."
        return f"about {minutes} minutes this session."

    def _intent_pc_health(self) -> str:
        try:
            import psutil  # type: ignore
        except Exception:
            return "cannot read system metrics right now."
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            mem_used = int(mem.percent)
            battery_text = ""
            if hasattr(psutil, "sensors_battery"):
                try:
                    bat = psutil.sensors_battery()
                except Exception:
                    bat = None
                if bat is not None:
                    battery_text = f", battery {int(bat.percent)}%"
            return f"CPU {int(cpu)}%, RAM {mem_used}% used{battery_text}."
        except Exception:
            return "system health check failed."

    def _intent_today_summary(self) -> str:
        today = time.strftime("%Y-%m-%d", time.localtime())
        try:
            interactions, fixes, summary = self._memory_db.get_session_summary(today)
        except Exception:
            interactions, fixes, summary = 0, 0, ""
        if not summary:
            if interactions or fixes:
                summary = f"today: {interactions} interactions, {fixes} fixes."
            else:
                summary = "no interactions logged yet today."
        return summary

    def _intent_git_status(self) -> str:
        try:
            status = self._code_ops.git_status()
        except Exception as exc:
            return f"git status failed: {exc}"
        return status or "git status empty."

    def _intent_todos(self) -> str:
        """
        Simple TODO scanner: grep-like search in .py/.md/.txt files under project root.
        """
        root = "."
        patterns = (".py", ".md", ".txt")
        todos: list[str] = []
        try:
            import os

            for dirpath, _, filenames in os.walk(root):
                # Skip virtualenv and runtime/cache dirs
                if any(skip in dirpath for skip in (".venv", ".git", "runtime", ".pytest_cache", ".tmp")):
                    continue
                for name in filenames:
                    if not name.lower().endswith(patterns):
                        continue
                    full = os.path.join(dirpath, name)
                    try:
                        with open(full, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if "TODO" in line or "todo" in line:
                                    snippet = line.strip()
                                    if len(snippet) > 120:
                                        snippet = snippet[:117] + "..."
                                    rel = os.path.relpath(full, root)
                                    todos.append(f"{rel}: {snippet}")
                                    if len(todos) >= 10:
                                        raise StopIteration
                    except StopIteration:
                        raise
                    except Exception:
                        continue
        except StopIteration:
            pass
        except Exception:
            return "todo scan failed."

        if not todos:
            return "no TODOs found."
        header = "top TODOs:\n"
        body = "\n".join(todos)
        return f"{header}{body}"

    def _intent_whats_open(self) -> str:
        """
        Lightweight 'what's open' using recent interactions + current active window title.
        Full window enumeration would need a separate integration.
        """
        from screensense.core.window_context import get_active_window_context

        try:
            active = get_active_window_context()
        except Exception:
            active = None

        active_desc = ""
        if active and (active.title or active.process_name):
            active_desc = f"active: {active.process_name or 'app'} — {active.title or ''}"

        recent = self._memory_db.recent_interactions(limit=3)
        if not active_desc and not recent:
            return "no open activity I can see."
        parts: list[str] = []
        if active_desc:
            parts.append(active_desc)
        if recent:
            parts.append("recent: " + "; ".join(recent))
        return ". ".join(parts)

    def _summarise_search_results(self, *, user_text: str, results: str) -> str:
        """
        Deterministic summary of search results.
        Expects results in TITLE/URL/SNIPPET blocks from BrowserOps.search_web_api.
        """
        # Split on TITLE markers.
        blocks = re.split(r"\bTITLE:\s*", results)
        entries: list[tuple[str, str]] = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # First line up to newline is title; next URL: line if present.
            lines = block.splitlines()
            title = lines[0].strip()
            url = ""
            for line in lines[1:]:
                if line.upper().startswith("URL:"):
                    url = line.split(":", 1)[1].strip()
                    break
            if title:
                entries.append((title, url))
            if len(entries) >= 3:
                break
        if not entries:
            return "search returned nothing."
        parts = []
        parts.append(f"search for: {user_text.strip()}")
        parts.append("top results:")
        for title, url in entries[:2]:
            if url:
                parts.append(f"{title} — {url}")
            else:
                parts.append(title)
        return " ".join(parts)

    def _summarise_page(self, *, url: str, content: str) -> str:
        """
        Deterministic short summary of a fetched page using simple heuristics.
        """
        text = re.sub(r"\s+", " ", content).strip()
        if not text:
            return f"opened {url} but page content was empty."
        # Take first ~220 chars as a pseudo-summary.
        snippet = text[:220].rstrip()
        return f"page {url} says: {snippet}"

    def _build_chat_prompt(
        self,
        *,
        user_text: str,
        ui_context: dict[str, object],
        session_goal: str,
        history: list[tuple[str, str]],
        web_result: str = "",
    ) -> str:
        ui_context = ui_context or {}
        app = str(ui_context.get("active_app") or "unknown")
        file = str(ui_context.get("current_file") or "")
        project = str(ui_context.get("project") or "")
        window_title = str(ui_context.get("window_title") or "")
        terminal_text = str(ui_context.get("terminal_output") or "")[:200]
        errors = str(ui_context.get("error_list") or "")[:200]
        
        # Build context description
        context_parts = []
        if app:
            context_parts.append(f"App: {app}")
        if file:
            context_parts.append(f"File: {file}")
        if project:
            context_parts.append(f"Project: {project}")
        if window_title:
            context_parts.append(f"Window: {window_title}")
        if terminal_text:
            context_parts.append(f"Terminal: {terminal_text}")
        if errors:
            context_parts.append(f"Errors: {errors}")
        
        context_str = " | ".join(context_parts) if context_parts else "Desktop"
        
        # Include recent history for context
        history_str = ""
        if history:
            recent = history[-3:]  # Last 3 exchanges
            history_str = "\n".join([f"user: {u}\naria: {a}" for u, a in recent])
            history_str = f"{history_str}\n---\n"
        
        # Build prompt
        base = (
            f"You are ARIA, {self._settings.user_name}'s desktop AI assistant.\n"
            f"Current screen context: {context_str}\n"
            f"Session goal: {session_goal or 'none'}\n\n"
            f"{history_str}"
            f"user: {user_text}\n"
            f"aria:"
        )
        
        if web_result.strip():
            base += f"\n[Web search results: {web_result[:500]}]"
        
        return base
    def _generate_response(self, prompt: str) -> str:
        """Generate response using LocalQwenInferenceClient with verified perception"""
        if self._settings.reasoning_mode in {"local", "hybrid"}:
            # Use verified perception through inference client
            try:
                # Capture current screen
                capturer = self._get_capturer()
                frame = capturer.capture_rgb()
                
                # Build context from prompt
                context = {
                    "user_name": self._settings.user_name,
                    "project_name": "screensense",
                    "session_goal": self._get_today_goal() or "none",
                }
                
                # Extract window context from prompt
                if "App:" in prompt:
                    parts = prompt.split("App:")[1].split("|")[0].strip()
                    context["process_name"] = parts
                if "Window:" in prompt:
                    parts = prompt.split("Window:")[1].split("|")[0].strip()
                    context["window_title"] = parts
                
                # Use inference client with verified perception
                decision = self._inference_client.analyze(frame, app_context=context)
                
                # Return the message from decision
                if decision.message.strip():
                    return decision.message
                
                # Fallback to old method if no message
                return self._generate_local_qwen_fallback(prompt)
            except Exception as e:
                print(f"[TG] Inference client failed: {e}")
                return self._generate_local_qwen_fallback(prompt)
        
        if self._settings.reasoning_mode in {"gemini", "hybrid"}:
            return self._generate_gemini(prompt)
        return ""
    
    def _generate_local_qwen_fallback(self, prompt: str) -> str:
        """Fallback to direct Ollama API call"""
        if self._settings.local_llm_provider != "ollama":
            return ""
        try:
            try:
                print(f"[PROMPT SENT]: {prompt[:800]}")
            except Exception:
                pass
            response = requests.post(
                f"{self._settings.local_llm_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self._settings.local_llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are ARIA, a laptop AI that speaks in 2-3 sentence descriptive observations "
                                "about the CURRENT screen. Be specific and reference actual facts. "
                                "Provide actionable insights when possible."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 512},
                },
                timeout=self._settings.local_llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            msg = data.get("message") or {}
            content = msg.get("content", "")
            if isinstance(content, list):
                raw = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                ).strip()
            else:
                raw = str(content or "").strip()
            try:
                print(f"[QWEN RAW]: {raw[:200]}")
            except Exception:
                pass
            cleaned = clean_response(raw)
            try:
                print(f"[QWEN CLEAN]: {cleaned}")
            except Exception:
                pass
            return cleaned
        except Exception:
            self._record_error("local_llm_failed")
            return ""

    def _generate_gemini(self, prompt: str) -> str:
        if not self._settings.gemini_api_key.strip():
            return ""
        try:
            from google import genai
        except Exception:
            return ""
        try:
            client = genai.Client(api_key=self._settings.gemini_api_key)
            raw = client.models.generate_content(
                model=self._settings.gemini_model,
                contents=[{"text": prompt}],
            )
            return str(raw.text or "").strip()
        except Exception:
            self._record_error("gemini_failed")
            return ""

    def _execute_pending_action(self) -> str:
        action_fn = self._pending_action.action_fn
        if action_fn is None:
            return "no action queued."
        try:
            result = action_fn()
        except Exception as exc:
            return f"action failed: {exc}"
        return result or "done."

    def _log_skip(self) -> None:
        self._memory_db.add_telegram_message(role="assistant", content="skipped")

    def _build_status_summary(self) -> str:
        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day).timestamp()
        count = self._memory_db.interaction_count_since(day_start)
        latest = self._memory_db.latest_interaction()
        goal = self._get_today_goal() or "no goal set"
        if latest:
            latest_text = (
                f"Latest: {latest.app} / {latest.aria_message} "
                f"({latest.outcome or 'unknown'})."
            )
        else:
            latest_text = "No interactions logged yet."
        return f"Today has {count} interactions. Goal: {goal}. {latest_text}"

    def _get_today_goal(self) -> str:
        return self._memory_db.get_goal(self._today_key())

    @staticmethod
    def _today_key() -> str:
        return time.strftime("%Y-%m-%d", time.localtime())

    def _days_to_deadline(self, now: datetime) -> int | None:
        if not self._settings.deadline_date:
            return None
        try:
            deadline = datetime.fromisoformat(self._settings.deadline_date).date()
        except ValueError:
            return None
        return (deadline - now.date()).days

    def _get_capturer(self) -> ScreenCapturer:
        capturer = getattr(self._capture_local, "capturer", None)
        if capturer is None:
            capturer = ScreenCapturer()
            self._capture_local.capturer = capturer
        return capturer

    def _record_error(self, message: str) -> None:
        self._last_error = message.strip()
        self._last_error_ts = time.time()

    def _store_exchange(self, user_text: str, response: str) -> None:
        if not user_text or response is None:
            return
        try:
            self._memory_db.add_telegram_message(role="user", content=user_text)
            self._memory_db.add_telegram_message(role="assistant", content=response)
        except Exception:
            pass

    def _approve_file_write(self, path: str, action_type: str) -> bool:
        preview = f"{action_type} {path}"
        return self._action_gate.approve(preview, "high")

    def set_goal_callback(self, callback: Callable[[str], str | None]) -> None:
        self._goal_callback = callback

    def set_health_callback(self, callback: Callable[[], str]) -> None:
        self._health_callback = callback

    def set_killlocal_callback(self, callback: Callable[[], str]) -> None:
        self._killlocal_callback = callback

    @staticmethod
    def _looks_like_token(token: str) -> bool:
        stripped = token.strip()
        if " " in stripped or "\n" in stripped or "\r" in stripped:
            return False
        if ":" not in stripped:
            return False
        if len(stripped) < 35:
            return False
        return True

    @staticmethod
    def _extract_error_text(ui_context: dict[str, object]) -> str:
        if not ui_context:
            return ""
        candidates = [
            str(ui_context.get("error_list") or ""),
            str(ui_context.get("terminal_last_output") or ""),
            str(ui_context.get("last_output") or ""),
            str(ui_context.get("any_dialog_text") or ""),
            str(ui_context.get("any_notification_text") or ""),
        ]
        for text in candidates:
            lowered = text.lower()
            if any(token in lowered for token in ("error", "exception", "traceback", "failed")):
                return text.strip()
        return ""



def _extract_url(msg: str) -> str | None:
    match = re.search(r"https?://[^\s]+", msg)
    if match:
        return match.group()

    match = re.search(
        r"\b([a-zA-Z0-9-]+\.(?:com|org|io|dev|net|ai|co|edu|gov))\b",
        msg,
    )
    if match:
        return "https://" + match.group()

    match = re.search(
        r"(?:open|visit|go to|browse)\s+([a-zA-Z0-9.-]+)",
        msg,
        re.IGNORECASE,
    )
    if match:
        name = match.group(1)
        if "." not in name:
            name = name + ".com"
        return "https://" + name

    return None


def _has_real_context(ui_context: dict[str, object]) -> bool:
    if not ui_context:
        return False
    ui_text = str(ui_context.get("ui_text") or "").strip()
    if ui_text:
        return True
    ocr = ui_context.get("ocr_context") or {}
    if isinstance(ocr, dict) and str(ocr.get("ui_text_excerpt") or "").strip():
        return True
    ui_ctx = ui_context.get("ui_context") or {}
    if isinstance(ui_ctx, dict) and ui_ctx:
        return True
    return False
