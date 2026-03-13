from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import threading
import time
from collections import deque

import requests

from screensense.agents.router import AgentRouter
from screensense.config import Settings
from screensense.core.action_executor import ActionExecutor
from screensense.core.action_policy import ActionPolicy
from screensense.core.anticipation import AnticipationEngine
from screensense.core.action_gate import ActionGate
from screensense.core.app_preferences import AppPreferenceStore, normalize_app_key
from screensense.core.audit_logger import AuditLogger
from screensense.core.capture import ScreenCapturer
from screensense.core.circuit_breaker import VisionCircuitBreaker
from screensense.core.session_lifecycle import SessionLifecycle
from screensense.core.health_monitor import HealthMonitor
from screensense.core.decision_freshness import is_stale_decision
from screensense.core.fast_path import FastPathGate
from screensense.core.goal_engine import GoalEngine
from screensense.core.interrupt_brain import InterruptBrain
from screensense.core.persona import PersonaAdapter
from screensense.core.presence import PresenceEngine
from screensense.core.rate_guard import GeminiRateGuard
from screensense.core.task_planner import TaskPlanner
from screensense.core.typing_detector import TypingDetector
from screensense.core.ui_context import UiContextExtractor, UiContextSettings
from screensense.core.window_context import get_active_window_context, is_blocked_title
from screensense.core.response_cleaner import clean_response, clean_response_proactive
from screensense.inference.base import InferenceClient
from screensense.inference.image_codec import encode_png_base64
from screensense.perception.semantic_change import score_semantic_change
from screensense.perception.ui_context import UiAutomationContext
from screensense.integrations.remote_approval import RemoteApprovalSettings, build_remote_approver
try:
    from screensense.integrations.telegram_bot import ARIATelegramBot
except Exception:  # pragma: no cover
    ARIATelegramBot = None  # type: ignore[assignment]
from screensense.integrations.voice import VoiceInput, VoiceOutput, VoiceSettings
from screensense.memory.persistence import ObservationPersister
from screensense.memory.store import RollingMemory
from screensense.memory.sqlite_store import SQLiteMemoryStore, hash_context
from screensense.models import ScreenObservation, VisionDecision
from screensense.orchestration.adk_runner import AgentRunner
from screensense.skills.file_ops import FileOps
from screensense.skills.code_ops import CodeOps
from screensense.skills.browser_ops import BrowserOps
from screensense.skills.system_ops import SystemOps

_shutdown = False


class RootCoordinator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._shutdown_event = threading.Event()
        (
            self._impact_threshold_effective,
            self._interrupt_cooldown_effective,
            self._dedupe_window_effective,
            self._semantic_dedupe_window_effective,
            self._max_interrupts_per_hour_effective,
            self._fast_path_user_active_diff_max_effective,
            self._fast_path_app_revisit_diff_max_effective,
        ) = self._tune_for_aggressiveness()
        self._capture_local = threading.local()
        self._typing = TypingDetector()
        self._voice = VoiceOutput(
            enabled=settings.enable_tts,
            settings=VoiceSettings(
                provider=settings.voice_provider,
                preset=settings.voice_preset,
                style=settings.voice_style,
                rate_wpm=settings.voice_rate_wpm,
                volume=settings.voice_volume,
                adaptive_mode=settings.voice_adaptive_mode,
                repeat_window_seconds=settings.voice_repeat_window_seconds,
                edge_voice=settings.voice_edge_name,
                edge_rate=settings.voice_edge_rate,
                edge_pitch=settings.voice_edge_pitch,
                coqui_model=settings.voice_coqui_model,
                coqui_speaker_wav=settings.voice_coqui_speaker_wav,
                coqui_language=settings.voice_coqui_language,
                coqui_device=settings.voice_coqui_device,
                piper_bin=settings.voice_piper_bin,
                piper_model_path=settings.voice_piper_model_path,
                piper_speaker_id=settings.voice_piper_speaker_id,
                piper_length_scale=settings.voice_piper_length_scale,
            ),
        )
        self._voice_input = VoiceInput(enabled=settings.enable_voice_input)
        self._remote_approver = build_remote_approver(
            RemoteApprovalSettings(
                provider=settings.remote_approval_provider,
                enabled=settings.enable_remote_approval,
                timeout_seconds=settings.remote_approval_timeout_seconds,
                poll_seconds=settings.remote_approval_poll_seconds,
                telegram_bot_token=settings.telegram_bot_token,
                telegram_chat_id=settings.telegram_chat_id,
            )
        )
        self._memory = RollingMemory(
            max_items=settings.memory_max_items,
            writer=ObservationPersister(
                sink_mode=settings.memory_sink_mode,
                local_path=settings.memory_local_path,
                firestore_project_id=settings.firestore_project_id,
                firestore_database=settings.firestore_database,
                firestore_collection=settings.firestore_memory_collection,
            ),
        )
        self._memory_db = SQLiteMemoryStore(settings.memory_sqlite_path)
        self._goal_engine = GoalEngine()
        self._presence = PresenceEngine(
            assistant_name=settings.assistant_name,
            assistant_persona=settings.assistant_persona,
            user_name=settings.user_name,
            project_name=settings.project_name,
            deadline_date=settings.deadline_date,
            away_idle_seconds=settings.away_idle_seconds,
            break_nudge_minutes=settings.break_nudge_minutes,
            break_nudge_repeat_minutes=settings.break_nudge_repeat_minutes,
        )
        self._anticipation = AnticipationEngine()
        self._persona = PersonaAdapter(
            enabled=settings.persona_learning_enabled,
            path=settings.persona_profile_path,
            assistant_name=settings.assistant_name,
            user_name=settings.user_name,
            base_persona=settings.assistant_persona,
        )
        self._app_prefs = AppPreferenceStore(
            enabled=settings.app_adaptation_enabled,
            path=settings.app_profile_path,
        )
        self._memory_digest = PresenceEngine.load_memory_digest(settings.memory_local_path)
        self._router = AgentRouter()
        self._runner = AgentRunner(
            router=self._router,
            runtime_mode=settings.agent_runtime_mode,
            strict=settings.agent_runtime_strict,
        )
        self._planner = TaskPlanner()
        self._executor = ActionExecutor(
            enabled=settings.enable_actions,
            mode=settings.product_mode,
        )
        self._action_policy = ActionPolicy(
            mode=settings.product_mode,
            ask_before_act=settings.ask_before_act,
            action_allowlist=settings.action_allowlist,
            auto_execute_max_risk=settings.auto_execute_max_risk,
        )
        self._audit = AuditLogger(
            enabled=settings.audit_logging_enabled,
            path=settings.audit_log_path,
            sink_mode=settings.audit_sink_mode,
            firestore_project_id=settings.firestore_project_id,
            firestore_database=settings.firestore_database,
            firestore_collection=settings.firestore_audit_collection,
        )
        self._inference_runtime_note = "configured"
        self._inference: InferenceClient = self._build_inference_client()
        self._interrupt_brain = InterruptBrain()
        self._rate_guard = GeminiRateGuard(
            min_interval_seconds=settings.gemini_min_call_interval_seconds,
            max_calls_per_minute=settings.gemini_max_calls_per_minute,
        )
        self._rate_guard_enabled = self._should_enable_rate_guard()
        self._vision_circuit = VisionCircuitBreaker(
            error_threshold=settings.vision_error_threshold,
            error_window_seconds=settings.vision_error_window_seconds,
            open_duration_seconds=settings.vision_circuit_open_seconds,
        )
        self._fast_path = FastPathGate(
            enabled=settings.fast_path_enabled,
            user_active_diff_max=self._fast_path_user_active_diff_max_effective,
            app_revisit_seconds=settings.fast_path_app_revisit_seconds,
            app_revisit_diff_max=self._fast_path_app_revisit_diff_max_effective,
        )
        self._vision_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="screensense-vision"
        )
        self._pending_vision_future: concurrent.futures.Future | None = None
        self._pending_vision_meta: dict[str, object] | None = None
        self._next_vision_eligible_ts = 0.0
        self._gemini_backoff_until = 0.0
        self._last_remote_alert_ts = 0.0
        self._last_inference_submit_ts = 0.0
        self._chat_history: deque[dict[str, str]] = deque(maxlen=10)
        self._chat_lock = threading.Lock()
        self._chat_context_cache: dict[str, object] | None = None
        self._chat_context_ts = 0.0
        self._ui_context_provider = UiAutomationContext()
        self._ocr_extractor = UiContextExtractor(
            UiContextSettings(
                enabled=self._settings.enable_ocr_context,
                provider=self._settings.ocr_provider,
                min_interval_seconds=self._settings.ocr_min_interval_seconds,
                max_text_chars=self._settings.ocr_max_text_chars,
            )
        )
        self._prev_ui_context: dict[str, object] | None = None
        self._last_rejection_reason = ""
        self._ipc_stop_event = threading.Event()
        self._ipc_clients: set = set()
        self._ipc_state: dict[str, str] = {"status": "Idle", "text": ""}
        self._telegram_bot = None
        if ARIATelegramBot is not None and settings.telegram_bot_token and settings.telegram_chat_id:
            self._telegram_bot = ARIATelegramBot(
                settings=settings,
                memory_db=self._memory_db,
                ui_context_provider=self._ui_context_provider,
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
            telegram_request_approval=(
                self._telegram_bot.request_approval if self._telegram_bot else None
            ),
            whisper_callback=self._whisper_approval,
            log_callback=self._audit.log,
        )
        self._file_ops = FileOps(approval_callback=self._approve_file_write)
        self._code_ops = CodeOps(self._action_gate)
        self._browser_ops = BrowserOps(self._action_gate)
        self._system_ops = SystemOps(self._action_gate)
        self._last_stackoverflow_text = ""
        self._last_stackoverflow_ts = 0.0
        self._stackoverflow_hint = ""
        self._safe_mode = False
        self._safe_mode_notified = False
        self._session_lifecycle = SessionLifecycle(
            memory_db=self._memory_db,
            voice=self._voice,
            deadline_date=settings.deadline_date,
            user_name=settings.user_name,
            send_telegram=self._telegram_bot.send_message if self._telegram_bot else None,
            whisper_callback=self._whisper_approval,
        )
        self._health = HealthMonitor(
            notify_callback=self._system_ops.show_notification if self._system_ops else None
        )
        self._health.note_telegram(bool(self._telegram_bot))
        self._health.note_browser(True)
        if self._telegram_bot:
            self._telegram_bot.set_goal_callback(self._handle_goal_capture)
            self._telegram_bot.set_health_callback(self._health.status_summary)
            self._telegram_bot.set_killlocal_callback(self._kill_local_llm)

    @property
    def shutdown_event(self) -> threading.Event:
        return self._shutdown_event

    def run_forever(self) -> None:
        self.run()

    def run(self) -> None:
        print(
            "[ScreenSense] started "
            f"(interval={self._settings.capture_interval_seconds}s, "
            f"diff_threshold={self._settings.diff_threshold_percent}%, "
            f"agent_runtime={self._runner.backend}) "
            f"note={self._runner.runtime_note}, "
            f"inference_note={self._inference_runtime_note}, "
            f"assistant={self._settings.assistant_name}, "
            f"user={self._settings.user_name}"
        )
        self._audit.log(
            "runner_initialized",
            {
                "backend": self._runner.backend,
                "runtime_note": self._runner.runtime_note,
                "runtime_mode": self._settings.agent_runtime_mode,
                "runtime_strict": self._settings.agent_runtime_strict,
                "voice_provider": self._voice.provider,
                "inference_mode": self._settings.inference_mode,
                "reasoning_mode": self._settings.reasoning_mode,
                "local_llm_provider": self._settings.local_llm_provider,
                "local_llm_model": self._settings.local_llm_model,
                "inference_runtime_note": self._inference_runtime_note,
                "rate_guard_enabled": self._rate_guard_enabled,
                "demo_force_speak": self._settings.demo_force_speak,
                "demo_force_infer_interval_seconds": self._settings.demo_force_infer_interval_seconds,
                "audit_sink_mode": self._settings.audit_sink_mode,
                "memory_sink_mode": self._settings.memory_sink_mode,
                "assistant_name": self._settings.assistant_name,
                "assistant_persona": self._settings.assistant_persona,
                "persona_learning_enabled": self._settings.persona_learning_enabled,
                "persona_profile_path": self._settings.persona_profile_path,
                "app_adaptation_enabled": self._settings.app_adaptation_enabled,
                "app_profile_path": self._settings.app_profile_path,
                "user_name": self._settings.user_name,
                "project_name": self._settings.project_name,
                "deadline_date": self._settings.deadline_date,
                "memory_digest": self._memory_digest,
                "remote_approval_enabled": self._settings.enable_remote_approval,
                "remote_approval_provider": self._settings.remote_approval_provider,
                "remote_alerts_enabled": self._settings.enable_remote_alerts,
                "fast_path_enabled": self._settings.fast_path_enabled,
                "ocr_context_enabled": self._settings.enable_ocr_context,
                "ocr_provider": self._settings.ocr_provider,
                "impact_scoring_enabled": self._settings.enable_impact_scoring,
                "impact_score_threshold": self._settings.impact_score_threshold,
                "voice_aggressiveness": self._settings.voice_aggressiveness,
                "impact_score_threshold_effective": round(self._impact_threshold_effective, 3),
                "interrupt_cooldown_effective": round(self._interrupt_cooldown_effective, 2),
                "dedupe_window_effective": round(self._dedupe_window_effective, 2),
                "semantic_dedupe_window_effective": round(self._semantic_dedupe_window_effective, 2),
                "max_interrupts_per_hour_effective": self._max_interrupts_per_hour_effective,
                "fast_path_user_active_diff_max_effective": round(
                    self._fast_path_user_active_diff_max_effective, 2
                ),
                "stale_decision_max_age_seconds": self._settings.stale_decision_max_age_seconds,
                "stale_decision_require_same_app": self._settings.stale_decision_require_same_app,
                "persona_profile": {
                    "proactive_bias": self._persona.profile.proactive_bias,
                    "brevity_bias": self._persona.profile.brevity_bias,
                    "directness_bias": self._persona.profile.directness_bias,
                    "trust_score": self._persona.profile.trust_score,
                },
            },
        )
        if self._settings.voice_startup_greeting:
            startup_line = self._settings.voice_startup_message or "Online."
            self._voice.speak_event(
                clean_response_proactive(startup_line),
                context=self._settings.assistant_name,
                confidence=0.99,
            )
            self._audit.log(
                "voice_startup_greeting",
                {"message": startup_line, "provider": self._voice.provider},
            )
        if self._telegram_bot:
            self._telegram_bot.start()
        self._session_lifecycle.on_startup()
        loop_count = 0
        
        # Start IPC WebSocket Server
        self._start_ipc_server()
        
        while not self._shutdown_event.is_set() and not _shutdown:
            loop_count += 1
            try:
                self._tick(loop_count)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self._audit.log("tick_error", {"error": str(exc)})
                time.sleep(0.2)

    def stop(self) -> None:
        global _shutdown
        _shutdown = True
        self._shutdown_event.set()
        self._ipc_stop_event.set()
        try:
            self._session_lifecycle.on_shutdown()
        except Exception:
            pass
        try:
            self._memory_db.close()
        except Exception:
            pass
        if self._telegram_bot:
            self._telegram_bot.stop()

    def request_shutdown(self) -> None:
        self.stop()

    def _tick(self, loop_count: int) -> None:
        self._broadcast_state("Idle")
        time.sleep(self._settings.capture_interval_seconds)
        self._poll_pending_inference()
        self._refresh_health()
        active_window = get_active_window_context()
        ui_result = (
            self._ui_context_provider.capture()
            if self._settings.ui_automation_enabled
            else None
        )
        ui_context = ui_result.context if ui_result else {}
        if not ui_context:
            ui_context = {
                "active_app": active_window.process_name or "",
                "window_title": active_window.title or "",
            }
        self._health.note_ui_automation(bool(ui_result and ui_result.ok))
        semantic = score_semantic_change(self._prev_ui_context, ui_context)
        self._prev_ui_context = ui_context
        change_score = semantic.score
        print(
            f"[ScreenSense] loop={loop_count} change_score={change_score:.2f} "
            f"reasons={','.join(semantic.reasons) if semantic.reasons else 'none'}"
        )
        user_idle = self._typing.is_idle(self._settings.typing_idle_seconds)
        self._presence.update_activity(user_idle=user_idle, changed_percent=change_score * 100)
        goal = self._goal_engine.summary()
        snapshot = self._presence.snapshot(goal=goal, memory_digest=self._memory_digest)
        self._session_lifecycle.on_tick(away=snapshot.away)
        break_nudge = self._presence.maybe_break_nudge(user_idle=user_idle)
        if break_nudge:
            self._voice.speak_event(
                clean_response_proactive(break_nudge),
                context="Wellbeing",
                confidence=0.95,
            )
            self._audit.log(
                "wellbeing_nudge",
                {
                    "message": break_nudge,
                    "session_minutes": self._presence.snapshot(
                        goal=self._goal_engine.summary(), memory_digest=self._memory_digest
                    ).session_minutes,
                },
            )
        motion_nudge = self._anticipation.note_motion(change_score * 100)
        if motion_nudge:
            print(f"[ScreenSense] anticipation: {motion_nudge}")
            self._audit.log(
                "anticipation_nudge",
                {
                    "kind": "high_motion",
                    "message": motion_nudge,
                    "change_score": round(change_score, 2),
                },
            )

        force_infer = False
        if self._settings.demo_force_infer_interval_seconds > 0:
            elapsed = time.time() - self._last_inference_submit_ts
            if elapsed >= self._settings.demo_force_infer_interval_seconds:
                force_infer = True

        if change_score <= 0.3 and not force_infer:
            self._audit.log(
                "semantic_change_skipped",
                {
                    "reason": "change_score_below_threshold",
                    "change_score": round(change_score, 2),
                    "reasons": semantic.reasons,
                },
            )
            return
        if force_infer and change_score <= 0.3:
            self._audit.log(
                "demo_force_inference",
                {
                    "change_score": round(change_score, 2),
                    "threshold": 0.3,
                    "interval_seconds": self._settings.demo_force_infer_interval_seconds,
                },
            )

        active_title = active_window.title
        if self._settings.focus_mode:
            print("[ScreenSense] focus mode active, skipped Gemini call")
            self._audit.log(
                "vision_skipped_focus_mode",
                {
                    "active_window_title": active_title,
                    "active_process_name": active_window.process_name,
                    "active_executable_name": active_window.executable_name,
                    "active_pid": active_window.pid,
                    "change_score": round(change_score, 2),
                },
            )
            return

        if is_blocked_title(active_title, self._settings.app_title_blocklist):
            print(f"[ScreenSense] blocked app title matched, skipped: {active_title}")
            self._audit.log(
                "vision_skipped_app_blocklist",
                {
                    "active_window_title": active_title,
                    "active_process_name": active_window.process_name,
                    "active_executable_name": active_window.executable_name,
                    "active_pid": active_window.pid,
                    "change_score": round(change_score, 2),
                },
            )
            return

        fast_path_reason = self._fast_path.should_skip(
            user_idle=user_idle,
            changed_percent=change_score * 100,
            app_key=f"{active_window.process_name}|{active_window.title}",
        )
        if fast_path_reason:
            self._audit.log(
                "vision_skipped_fast_path",
                {
                    "reason": fast_path_reason,
                    "change_score": round(change_score, 2),
                    "active_window_title": active_window.title,
                    "active_process_name": active_window.process_name,
                },
            )
            return

        if self._pending_vision_future is not None and not self._pending_vision_future.done():
            self._audit.log(
                "vision_skipped_inflight",
                {
                    "reason": "inflight_request",
                    "change_score": round(change_score, 2),
                    "active_window_title": active_title,
                },
            )
            return

        now = time.time()
        if now < self._next_vision_eligible_ts:
            retry_after = round(max(0.0, self._next_vision_eligible_ts - now), 2)
            self._audit.log(
                "vision_skipped_backoff_window",
                {
                    "reason": "retry_backoff_window",
                    "retry_after_seconds": retry_after,
                    "change_score": round(change_score, 2),
                },
            )
            return

        circuit = self._vision_circuit.check()
        if not circuit.allow:
            print(
                "[ScreenSense] skipped Gemini call "
                f"({circuit.reason}, retry_after={circuit.retry_after_seconds}s)"
            )
            self._audit.log(
                "vision_skipped_circuit_breaker",
                {
                    "reason": circuit.reason,
                    "retry_after_seconds": circuit.retry_after_seconds,
                    "change_score": round(change_score, 2),
                },
            )
            return

        ui_text = ui_result.text if ui_result else ""
        if not ui_text and self._settings.enable_ocr_context:
            try:
                ocr_context = self._ocr_extractor.enrich(
                    frame_rgb=self._get_capturer().capture_rgb(),
                    app_context={},
                )
                ui_text = str(ocr_context.get("ui_text_excerpt") or "")
            except Exception:
                pass
        visual_only = bool(
            active_window.process_name
            and any(
                token in active_window.process_name.lower()
                for token in self._settings.visual_only_apps
            )
        )
        gemini_allowed = bool(
            (ui_result is None or not ui_result.ok)
            or visual_only
            or (change_score > 0.8 and len(ui_text) < 100)
        )
        if time.time() < self._gemini_backoff_until:
            gemini_allowed = False

        if self._rate_guard_enabled and gemini_allowed:
            rate_guard = self._rate_guard.check()
            if not rate_guard.allowed:
                print(
                    "[ScreenSense] skipped Gemini call "
                    f"({rate_guard.reason}, retry_after={rate_guard.retry_after_seconds}s)"
                )
                self._audit.log(
                    "vision_skipped_rate_guard",
                    {
                        "reason": rate_guard.reason,
                        "retry_after_seconds": rate_guard.retry_after_seconds,
                        "change_score": round(change_score, 2),
                    },
                )
                return

        goal = snapshot.goal
        current = self._get_capturer().capture_rgb()
        stack_hint = self._maybe_update_stackoverflow_hint(ui_context)
        app_context = {
            "window_title": active_window.title,
            "process_name": active_window.process_name,
            "executable_name": active_window.executable_name,
            "pid": active_window.pid,
            "ui_context_json": ui_context,
            "ui_context_text": ui_text,
            "ui_context_length": len(ui_text),
            "ui_text_excerpt": ui_text,
            "ui_text_cached": False,
            "gemini_allowed": gemini_allowed,
            "recent_memory": self._memory_db.recent_interactions(limit=5),
            "last_rejection": self._memory_db.last_rejection(
                active_window.process_name or "unknown"
            ),
            "preference_matches": self._memory_db.top_preferences(
                active_window.process_name or "unknown",
                limit=3,
            ),
            "recent_agent_messages": [
                item.decision.message
                for item in self._memory.recent()[-4:]
                if item.decision.message.strip()
            ],
            **self._presence.to_inference_context(snapshot),
        }
        if stack_hint:
            app_context["stackoverflow_hint"] = stack_hint
        self._broadcast_state("Analyzing")
        self._pending_vision_future = self._vision_executor.submit(
            self._analyze_with_source,
            current.copy(),
            app_context,
        )
        self._last_inference_submit_ts = time.time()
        self._fast_path.note_inference_submitted(
            f"{active_window.process_name}|{active_window.title}"
        )
        self._pending_vision_meta = {
            "diff": change_score * 100,
            "active_window_title": active_window.title,
            "active_process_name": active_window.process_name,
            "user_idle_at_capture": user_idle,
            "submitted_ts": time.time(),
            "submitted_app_key": normalize_app_key(
                active_window.process_name,
                active_window.title,
            ),
        }
        self._audit.log(
            "vision_submitted_async",
            {
                "change_score": round(change_score, 2),
                "active_window_title": active_window.title,
            },
        )

    def _confirm_action(self, action_description: str, *, reason: str, user_away: bool) -> bool:
        if user_away and self._settings.enable_remote_approval:
            self._voice.speak(
                clean_response_proactive("Approval sent to your phone. Waiting for response.")
            )
            remote = self._remote_approver.request_approval(
                action_description=action_description,
                reason=reason,
            )
            self._audit.log(
                "remote_approval_result",
                {
                    "description": action_description,
                    "provider": self._settings.remote_approval_provider,
                    "result": remote,
                },
            )
            if remote is not None:
                return remote
            return False
        if self._voice_input.available:
            self._voice.speak(clean_response_proactive("Say yes to approve, or no to cancel."))
            heard = self._voice_input.listen_yes_no(
                timeout_seconds=self._settings.voice_confirm_timeout_seconds
            )
            if heard is not None:
                return heard
        response = input(f"Allow action? {action_description} [y/N]: ").strip().lower()
        return response in {"y", "yes"}

    def _poll_pending_inference(self) -> None:
        if self._pending_vision_future is None:
            return
        if not self._pending_vision_future.done():
            return

        future = self._pending_vision_future
        meta = self._pending_vision_meta or {}
        self._pending_vision_future = None
        self._pending_vision_meta = None

        try:
            decision, inference_source = future.result()
        except Exception as exc:
            retry_after = self._infer_retry_seconds(exc)
            self._next_vision_eligible_ts = time.time() + retry_after
            self._gemini_backoff_until = time.time() + retry_after
            circuit_result = self._vision_circuit.record_error()
            print(
                "[ScreenSense] vision error "
                f"({type(exc).__name__}), backing off {retry_after}s"
            )
            self._audit.log(
                "vision_error",
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "retry_after_seconds": retry_after,
                    "circuit_result": circuit_result.reason,
                },
            )
            anticipation = self._anticipation.nudge_for_error(exc)
            if anticipation:
                self._voice.speak_event(
                    clean_response_proactive(anticipation),
                    context="Runtime",
                    confidence=0.99,
                )
                self._audit.log(
                    "anticipation_nudge",
                    {"kind": "runtime_error", "message": anticipation},
                )
            if circuit_result.reason == "vision_circuit_opened":
                print(
                    "[ScreenSense] circuit breaker opened "
                    f"for {circuit_result.retry_after_seconds}s"
                )
                self._audit.log(
                    "vision_circuit_opened",
                    {"open_seconds": circuit_result.retry_after_seconds},
                )
            return

        self._vision_circuit.record_success()
        changed_percent = float(meta.get("diff", 0.0))
        active_window_title = str(meta.get("active_window_title", "Unknown"))
        active_process_name = str(meta.get("active_process_name", "unknown"))
        submitted_ts = float(meta.get("submitted_ts", time.time()))
        submitted_app_key = str(meta.get("submitted_app_key", ""))
        current_window = get_active_window_context()
        current_app_key = normalize_app_key(current_window.process_name, current_window.title)
        stale, stale_reason = is_stale_decision(
            submitted_ts=submitted_ts,
            max_age_seconds=self._settings.stale_decision_max_age_seconds,
            submitted_app_key=submitted_app_key,
            current_app_key=current_app_key,
            require_same_app=self._settings.stale_decision_require_same_app,
        )
        if stale:
            self._audit.log(
                "decision_dropped_stale",
                {
                    "reason": stale_reason,
                    "changed_percent": round(changed_percent, 2),
                    "submitted_app_key": submitted_app_key,
                    "current_app_key": current_app_key,
                    "decision_context": decision.context,
                },
            )
            return
        self._handle_decision_flow(
            decision=decision,
            changed_percent=changed_percent,
            active_window_title=active_window_title,
            active_process_name=active_process_name,
            inference_source=inference_source,
        )

    def _handle_decision_flow(
        self,
        *,
        decision: VisionDecision,
        changed_percent: float,
        active_window_title: str,
        active_process_name: str,
        inference_source: str,
    ) -> None:
        self._memory.add(ScreenObservation(changed_percent=changed_percent, decision=decision))
        goal = self._goal_engine.update(decision, active_window_title=active_window_title)
        snapshot = self._presence.snapshot(goal=goal, memory_digest=self._memory_digest)
        user_idle = self._typing.is_idle(self._settings.typing_idle_seconds)
        app_key = normalize_app_key(active_process_name, active_window_title)
        threshold_for_app = self._app_prefs.threshold_for(
            base_threshold=self._settings.impact_score_threshold,
            app_key=app_key,
        )
        typing_seconds = self._typing.seconds_since_last_keypress()
        interrupt = self._interrupt_brain.evaluate(
            decision=decision,
            confidence=decision.confidence,
            typing_seconds_since=typing_seconds,
            session_minutes=snapshot.session_minutes,
        )
        if not interrupt.allow_interrupt and not self._settings.demo_force_speak:
            self._audit.log(
                "interrupt_evaluated",
                {
                    "allow_interrupt": False,
                    "reason": interrupt.reason,
                    "interrupt_score": round(interrupt.score, 3),
                    "impact_score": round(interrupt.impact, 3),
                    "urgency_score": round(interrupt.urgency, 3),
                    "receptivity_score": round(interrupt.receptivity, 3),
                    "changed_percent": round(changed_percent, 2),
                    "context": decision.context,
                    "domain": decision.domain,
                    "priority": decision.priority,
                    "confidence": decision.confidence,
                    "message": decision.message,
                    "inference_source": inference_source,
                    "app_profile": self._app_prefs.snapshot(app_key),
                    "goal": goal,
                    "away": snapshot.away,
                    "session_minutes": snapshot.session_minutes,
                },
            )
            return
        self._audit.log(
            "interrupt_evaluated",
            {
                "allow_interrupt": True,
                "reason": interrupt.reason if not self._settings.demo_force_speak else "demo_force_speak_override",
                "interrupt_score": round(interrupt.score, 3),
                "impact_score": round(interrupt.impact, 3),
                "urgency_score": round(interrupt.urgency, 3),
                "receptivity_score": round(interrupt.receptivity, 3),
                "changed_percent": round(changed_percent, 2),
                "context": decision.context,
                "domain": decision.domain,
                "priority": decision.priority,
                "confidence": decision.confidence,
                "message": decision.message,
                "inference_source": inference_source,
                "app_profile": self._app_prefs.snapshot(app_key),
                "goal": goal,
                "away": snapshot.away,
                "session_minutes": snapshot.session_minutes,
            },
        )

        self._interrupt_brain.record_interrupt()
        self._memory_db.add_interaction(
            app=active_process_name or "unknown",
            context_hash=hash_context(str(decision.context)),
            aria_message=decision.message,
            user_response="pending",
            action_taken="none",
            outcome="spoken",
        )
        if self._settings.voice_preset == "astra_like":
            spoken_message = decision.message.strip() or self._presence.compose_spoken_message(
                decision, goal=goal
            )
        else:
            spoken_message = self._presence.compose_spoken_message(decision, goal=goal)
            spoken_message = self._persona.compose_message(
                decision=decision,
                goal=goal,
                base_message=spoken_message,
            )
        spoken_message = clean_response_proactive(spoken_message)
        if self._safe_mode:
            self._broadcast_state("SafeMode", text=spoken_message)
            self._voice.speak_mode("earcon", mode="earcon", context="SafeMode")
            return
        self._maybe_send_remote_alert(
            decision=decision,
            snapshot_away=snapshot.away,
            goal=goal,
            message=spoken_message,
        )
        self._broadcast_state("Speaking", text=spoken_message)
        voice_mode = self._select_voice_mode(
            priority=decision.priority,
            receptivity=interrupt.receptivity,
        )
        voiced = _voice_compose(spoken_message, decision)
        self._voice.speak_mode(
            clean_response_proactive(voiced),
            mode=voice_mode,
            context=decision.context,
            confidence=decision.confidence,
        )
        print(f"[ScreenSense] [{inference_source}] {decision.context}: {spoken_message}")

        runner_result = self._runner.run(decision.domain, decision)
        action = runner_result.action
        plan = self._planner.build(decision=decision, action=action, goal=goal)
        self._audit.log(
            "action_planned",
            {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "domain": decision.domain,
                "context": decision.context,
                "description": action.description,
                "executable": action.executable,
                "product_mode": self._settings.product_mode,
                "agent_runtime_backend": runner_result.backend,
                "agent_runtime_note": runner_result.runtime_note,
                "inference_source": inference_source,
                "plan_steps": [
                    {
                        "index": s.index,
                        "label": s.label,
                        "step_type": s.step_type,
                        "success_criteria": s.success_criteria,
                    }
                    for s in plan.steps
                ],
            },
        )
        self._audit.log(
            "plan_created",
            {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "domain": plan.domain,
                "step_count": len(plan.steps),
                "created_ts": plan.created_ts,
            },
        )
        action_decision = self._action_policy.evaluate(action)
        preview = self._executor.preview(action)
        print(f"[ScreenSense] action preview: {preview}")
        self._audit.log(
            "action_evaluated",
            {
                "should_execute": action_decision.should_execute,
                "requires_confirmation": action_decision.requires_confirmation,
                "reason": action_decision.reason,
                "description": action.description,
                "action_type": action.action_type,
                "risk": action.risk,
                "inference_source": inference_source,
                "plan_id": plan.plan_id,
            },
        )

        if not action_decision.should_execute:
            print(f"[ScreenSense] action skipped: {action_decision.reason}")
            self._audit.log(
                "action_skipped",
                {
                    "reason": action_decision.reason,
                    "description": action.description,
                    "plan_id": plan.plan_id,
                },
            )
            if action_decision.reason:
                self._last_rejection_reason = action_decision.reason
            self._memory_db.add_interaction(
                app=active_process_name or "unknown",
                context_hash=hash_context(str(decision.context)),
                aria_message=decision.message,
                user_response="rejected",
                action_taken=action.description,
                outcome="skipped",
            )
            self._memory_db.update_preference(
                pattern=f"app:{active_process_name or 'unknown'}",
                sentiment="disliked",
            )
            self._interrupt_brain.record_rejection()
            self._persona.record_feedback(event="action_skipped", reason=action_decision.reason)
            self._app_prefs.record_feedback(
                app_key=app_key,
                event="action_skipped",
                reason=action_decision.reason,
            )
            return

        if action_decision.requires_confirmation and not self._confirm_action(
            action.description,
            reason=decision.message,
            user_away=snapshot.away,
        ):
            print(f"[ScreenSense] user denied action: {action.description}")
            self._audit.log(
                "action_denied",
                {"description": action.description, "plan_id": plan.plan_id},
            )
            self._last_rejection_reason = "action_denied"
            self._memory_db.add_interaction(
                app=active_process_name or "unknown",
                context_hash=hash_context(str(decision.context)),
                aria_message=decision.message,
                user_response="rejected",
                action_taken=action.description,
                outcome="denied",
            )
            self._memory_db.update_preference(
                pattern=f"app:{active_process_name or 'unknown'}",
                sentiment="disliked",
            )
            self._interrupt_brain.record_rejection()
            self._persona.record_feedback(event="action_denied")
            self._app_prefs.record_feedback(app_key=app_key, event="action_denied")
            return

        result = self._executor.execute(action)
        print(
            "[ScreenSense] action result "
            f"executed={result.executed} verified={result.verified}: {action.description}"
        )
        if result.executed and not result.verified:
            self._audit.log(
                "action_verification_failed",
                {
                    "description": action.description,
                    "verification_reason": result.verification_reason,
                    "verification_attempts": result.verification_attempts,
                    "inference_source": inference_source,
                    "plan_id": plan.plan_id,
                },
            )
        self._audit.log(
            "action_executed",
            {
                "plan_id": plan.plan_id,
                "description": action.description,
                "executed": result.executed,
                "verified": result.verified,
                "error": result.error,
                "verification_reason": result.verification_reason,
                    "verification_attempts": result.verification_attempts,
                    "verification_hint": action.verification_hint,
                    "inference_source": inference_source,
                    "step_results": [
                        {
                            "index": item.index,
                            "step_type": item.step_type,
                            "success": item.success,
                            "error": item.error,
                        }
                        for item in (result.step_results or [])
                    ],
            },
        )
        self._memory_db.add_interaction(
            app=active_process_name or "unknown",
            context_hash=hash_context(str(decision.context)),
            aria_message=decision.message,
            user_response="accepted",
            action_taken=action.description,
            outcome="executed",
        )
        self._memory_db.update_preference(
            pattern=f"app:{active_process_name or 'unknown'}",
            sentiment="liked",
        )
        self._interrupt_brain.record_accept()
        self._persona.record_feedback(event="action_executed")
        self._app_prefs.record_feedback(app_key=app_key, event="action_executed")

    def _analyze_with_source(
        self,
        frame_rgb,
        app_context: dict[str, str | int | bool | None] | None,
    ) -> tuple[VisionDecision, str]:
        decision = self._inference.analyze(frame_rgb=frame_rgb, app_context=app_context)
        source = str(getattr(self._inference, "last_source", self._settings.reasoning_mode))
        escalate_reason = str(getattr(self._inference, "last_escalation_reason", "")).strip()
        if source == "gemini" and escalate_reason:
            source = f"{source}:{escalate_reason}"
        return decision, source

    @staticmethod
    def _select_voice_mode(*, priority: str, receptivity: float) -> str:
        hour = time.localtime().tm_hour
        if priority == "critical":
            return "speak"
        if 0 <= hour < 6:
            return "whisper"
        if receptivity < 0.4:
            return "earcon"
        if receptivity < 0.7:
            return "whisper"
        return "speak"

    def _maybe_send_remote_alert(
        self,
        *,
        decision: VisionDecision,
        snapshot_away: bool,
        goal: str,
        message: str,
    ) -> None:
        if not self._settings.enable_remote_alerts:
            return
        if not snapshot_away:
            return
        if self._settings.remote_alert_min_priority == "critical" and decision.priority != "critical":
            return
        now = time.time()
        if (now - self._last_remote_alert_ts) < self._settings.remote_alert_cooldown_seconds:
            return
        if not message:
            message = decision.message or "alert"
        alert_text = clean_response_proactive(
            (
                "ScreenSense alert\n"
                f"Priority: {decision.priority}\n"
                f"Context: {decision.context}\n"
                f"Message: {decision.message}\n"
                f"Goal: {goal}"
            )
        )
        sent = self._remote_approver.notify(alert_text)
        if self._telegram_bot:
            self._telegram_bot.send_proactive_alert(
                message=message,
                reasoning=decision.message,
                action_fn=None,
            )
        self._last_remote_alert_ts = now
        self._audit.log(
            "remote_alert_sent",
            {
                "sent": sent,
                "priority": decision.priority,
                "context": decision.context,
            },
        )

    @staticmethod
    def _infer_retry_seconds(exc: Exception) -> int:
        status_code = getattr(exc, "status_code", None)
        message = str(exc)
        if status_code == 429:
            match = re.search(r"retry in ([0-9]+(?:\\.[0-9]+)?)s", message.lower())
            if match:
                return max(5, int(float(match.group(1))))
            return 60
        if status_code == 400 and "api key not valid" in message.lower():
            return 120
        return 15

    def _build_inference_client(self) -> InferenceClient:
        local_client = self._build_local_qwen_client()

        gemini_available = self._is_gemini_available()
        if self._settings.reasoning_mode == "local":
            self._inference_runtime_note = "local_qwen_only"
            return local_client
        if self._settings.reasoning_mode == "hybrid":
            if not gemini_available:
                self._inference_runtime_note = (
                    "hybrid_requested_but_gemini_unavailable; falling back to local_qwen_only"
                )
                return local_client
            from screensense.inference.hybrid_inference import HybridInferenceClient
            self._inference_runtime_note = "hybrid_local_qwen_plus_gemini"
            return HybridInferenceClient(
                local_client=local_client,
                gemini_client=self._build_gemini_inference_client(),
                escalate_confidence_threshold=self._settings.local_llm_escalate_confidence_threshold,
                force_gemini_on_critical=self._settings.hybrid_force_gemini_on_critical,
            )
        if not gemini_available:
            self._inference_runtime_note = (
                "gemini_requested_but_unavailable; falling back to local_qwen_only"
            )
            return local_client
        self._inference_runtime_note = "gemini_only"
        return self._build_gemini_inference_client()

    def _build_local_qwen_client(self) -> InferenceClient:
        from screensense.inference.local_qwen import LocalQwenInferenceClient

        return LocalQwenInferenceClient(
            provider=self._settings.local_llm_provider,
            model=self._settings.local_llm_model,
            base_url=self._settings.local_llm_base_url,
            timeout_seconds=self._settings.local_llm_timeout_seconds,
            use_vision=self._settings.local_llm_use_vision,
            ui_context_extractor=self._build_ui_context_extractor(),
        )

    def _is_gemini_available(self) -> bool:
        if self._settings.inference_mode == "http":
            return True
        return bool(self._settings.gemini_api_key.strip())

    def _build_gemini_inference_client(self) -> InferenceClient:
        if self._settings.inference_mode == "http":
            from screensense.inference.http_inference import HttpInferenceClient

            return HttpInferenceClient(
                base_url=self._settings.inference_backend_url,
                timeout_seconds=self._settings.inference_timeout_seconds,
                auth_token=self._settings.inference_backend_auth_token,
            )
        from screensense.inference.local_inference import LocalGeminiInferenceClient

        return LocalGeminiInferenceClient(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            ui_context_extractor=self._build_ui_context_extractor(),
        )

    def _build_ui_context_extractor(self) -> UiContextExtractor:
        return UiContextExtractor(
            UiContextSettings(
                enabled=self._settings.enable_ocr_context,
                provider=self._settings.ocr_provider,
                min_interval_seconds=self._settings.ocr_min_interval_seconds,
                max_text_chars=self._settings.ocr_max_text_chars,
            )
        )

    def _should_enable_rate_guard(self) -> bool:
        if self._settings.reasoning_mode == "local":
            return False
        if self._settings.reasoning_mode == "hybrid":
            return self._is_gemini_available()
        return True

    def _tune_for_aggressiveness(self) -> tuple[float, float, float, float, int, float, float]:
        mode = self._settings.voice_aggressiveness
        impact_threshold = self._settings.impact_score_threshold
        cooldown = self._settings.interrupt_cooldown_seconds
        dedupe = self._settings.dedupe_window_seconds
        semantic_dedupe = self._settings.semantic_dedupe_window_seconds
        max_interrupts = self._settings.max_interrupts_per_hour
        fast_user_active_diff_max = self._settings.fast_path_user_active_diff_max
        fast_app_revisit_diff_max = self._settings.fast_path_app_revisit_diff_max

        if mode == "quiet":
            impact_threshold = min(0.9, impact_threshold + 0.08)
            cooldown = cooldown * 1.4
            dedupe = dedupe * 1.3
            semantic_dedupe = semantic_dedupe * 1.3
            max_interrupts = max(1, max_interrupts - 2)
        elif mode == "chatty":
            impact_threshold = max(0.35, impact_threshold - 0.12)
            cooldown = max(5.0, cooldown * 0.5)
            dedupe = max(45.0, dedupe * 0.55)
            semantic_dedupe = max(60.0, semantic_dedupe * 0.6)
            max_interrupts = max_interrupts + 4
            fast_user_active_diff_max = max(6.0, fast_user_active_diff_max * 0.4)
            fast_app_revisit_diff_max = max(10.0, fast_app_revisit_diff_max * 0.5)

        return (
            impact_threshold,
            cooldown,
            dedupe,
            semantic_dedupe,
            max_interrupts,
            fast_user_active_diff_max,
            fast_app_revisit_diff_max,
        )

    # ---- IPC Server ----
    def _start_ipc_server(self) -> None:
        def run_server():
            import websockets
            
            async def handler(websocket):
                self._ipc_clients.add(websocket)
                try:
                    await websocket.send(json.dumps(self._ipc_state))
                    async for message in websocket:
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        msg_type = str(payload.get("type") or "").strip()
                        if msg_type == "chat_open":
                            context = self._capture_chat_context(force=True)
                            response = {
                                "type": "chat_context",
                                "context": context.get("ui_context", {}),
                                "history": list(self._chat_history),
                            }
                            await websocket.send(json.dumps(response))
                        elif msg_type == "chat_request":
                            question = str(payload.get("question") or "").strip()
                            if not question:
                                continue
                            await self._handle_chat_request(websocket, question)
                        elif msg_type == "chat_close":
                            await websocket.send(json.dumps({"type": "chat_closed"}))
                        elif msg_type == "focus_mode":
                            enabled = bool(payload.get("enabled"))
                            self._settings.focus_mode = enabled
                        elif msg_type == "app_shutdown":
                            self.request_shutdown()
                            return
                except websockets.exceptions.ConnectionClosed:
                    pass
                finally:
                    self._ipc_clients.remove(websocket)

            async def main():
                async with websockets.serve(handler, "localhost", 8765):
                    while not self._ipc_stop_event.is_set():
                        await asyncio.sleep(0.5)
                    
            asyncio.run(main())
            
        threading.Thread(target=run_server, daemon=True, name="ScreenSense-IPC").start()

    def _get_capturer(self) -> ScreenCapturer:
        capturer = getattr(self._capture_local, "capturer", None)
        if capturer is None:
            capturer = ScreenCapturer()
            self._capture_local.capturer = capturer
        return capturer



    def _capture_chat_context(self, *, force: bool = False) -> dict[str, object]:
        now = time.time()
        with self._chat_lock:
            if not force and self._chat_context_cache and (now - self._chat_context_ts) < 12:
                return self._chat_context_cache

            frame = self._get_capturer().capture_rgb()
            active_window = get_active_window_context()
            goal = self._goal_engine.summary()
            snapshot = self._presence.snapshot(goal=goal, memory_digest=self._memory_digest)
            app_context = {
                "window_title": active_window.title,
                "process_name": active_window.process_name,
                "executable_name": active_window.executable_name,
                "pid": active_window.pid,
                **self._presence.to_inference_context(snapshot),
            }
            ui_result = (
                self._ui_context_provider.capture()
                if self._settings.ui_automation_enabled
                else None
            )
            ui_text = ui_result.text if ui_result else ""
            ui_context = {
                "active_app": active_window.process_name or "",
                "window_title": active_window.title,
                "goal": goal,
                "ui_text_excerpt": ui_text,
                "now_iso": app_context.get("now_iso", ""),
                "session_minutes": app_context.get("session_minutes", 0),
            }
            payload = {
                "frame_rgb": frame,
                "app_context": {**app_context, "ui_context_text": ui_text},
                "ui_context": ui_context,
            }
            self._chat_context_cache = payload
            self._chat_context_ts = now
            return payload

    def _build_chat_prompt(
        self,
        *,
        question: str,
        app_context: dict[str, object],
    ) -> str:
        history_lines: list[str] = []
        for item in list(self._chat_history)[-10:]:
            role = item.get("role", "user").strip().lower()
            content = item.get("content", "").strip()
            if not content:
                continue
            prefix = "User" if role == "user" else "ARIA"
            history_lines.append(f"{prefix}: {content}")
        history_block = "\n".join(history_lines) if history_lines else "none"
        context_keys = [
            "window_title",
            "process_name",
            "executable_name",
            "assistant_name",
            "assistant_persona",
            "user_name",
            "project_name",
            "now_iso",
            "weekday",
            "time_block",
            "session_minutes",
            "away",
            "goal",
            "deadline_days_left",
            "memory_digest",
            "ui_ocr_enabled",
            "ui_ocr_provider",
            "ui_text_excerpt",
            "ui_text_cached",
            "stackoverflow_hint",
        ]
        context_lines = []
        for key in context_keys:
            if key in app_context:
                context_lines.append(f"- {key}: {app_context.get(key)}")
        context_block = "\n".join(context_lines)
        return (
            "You are ARIA. Shwet's co-pilot.\n"
            "NOT a chatbot. NOT an assistant.\n"
            "A presence that lives on his screen.\n\n"
            "RULES - non-negotiable:\n"
            "No bullet points. Ever.\n"
            "No numbered lists. Ever.\n"
            "No markdown in responses.\n"
            "No **, no #, no backticks in speech.\n"
            "No 'Here is what you can do'\n"
            "No 'feel free to ask'\n"
            "No 'I can help you with'\n"
            "Maximum 3 sentences for any response\n"
            "Talk like a person, not documentation\n"
            "Answer in English only.\n"
            "Never invent filenames, errors, or UI text.\n"
            "If the screen context is empty or unclear, say 'screen context unavailable'.\n"
            "\n"
            "You know:\n"
            "His name: Shwet\n"
            "His project: ScreenSense\n"
            f"Current screen: {context_block}\n"
            f"His goal: {app_context.get('goal') or 'none'}\n"
            f"Recent history: {history_block}\n"
            f"Time: {time.strftime('%H:%M', time.localtime())}\n\n"
            f"User question: {question}\n"
            "ARIA:"
        )

    async def _handle_chat_request(self, websocket, question: str) -> None:
        goal_response = self._handle_goal_capture(question)
        if goal_response:
            await websocket.send(json.dumps({"type": "chat_done", "response": goal_response}))
            self._voice.speak_event(
                clean_response_proactive(goal_response),
                context="Session",
            )
            return
        routed = self._route_chat_intent(question)
        if routed is not None:
            await websocket.send(json.dumps({"type": "chat_done", "response": routed}))
            self._voice.speak_event(
                clean_response_proactive(routed),
                context="Chat",
            )
            return
        if self._settings.local_llm_provider != "ollama":
            await websocket.send(
                json.dumps({"type": "chat_error", "error": "Local LLM provider disabled."})
            )
            return
        context = self._capture_chat_context()
        app_context = context.get("app_context") or {}
        if not self._has_real_chat_context(app_context):
            msg = "screen context unavailable. open the window and try again."
            await websocket.send(json.dumps({"type": "chat_done", "response": msg}))
            self._voice.speak_event(
                clean_response_proactive(msg),
                context="Session",
            )
            return
        frame_rgb = context.get("frame_rgb")
        prompt = self._build_chat_prompt(question=question, app_context=app_context)
        await websocket.send(json.dumps({"type": "chat_started", "question": question}))
        response_chunks: list[str] = []
        try:
            for chunk in self._stream_chat_response(prompt, frame_rgb):
                if chunk:
                    response_chunks.append(chunk)
                    await websocket.send(json.dumps({"type": "chat_chunk", "delta": chunk}))
        except Exception as exc:
            await websocket.send(json.dumps({"type": "chat_error", "error": str(exc)}))
            return
        full = "".join(response_chunks).strip()
        if not full:
            full = "I could not extract enough detail from the screen to answer."
        full = clean_response(full)
        with self._chat_lock:
            self._chat_history.append({"role": "user", "content": question})
            self._chat_history.append({"role": "assistant", "content": full})
        await websocket.send(json.dumps({"type": "chat_done", "response": full}))
        self._voice.speak_event(
            clean_response_proactive(full),
            context=str(app_context.get("window_title") or "Screen"),
        )

    def _stream_chat_response(self, prompt: str, frame_rgb):
        payload = {
            "model": self._settings.local_llm_model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0.2},
        }
        if frame_rgb is not None and self._settings.local_llm_use_vision and self._should_send_chat_vision():
            payload["images"] = [encode_png_base64(frame_rgb[::2, ::2])]
        with requests.post(
            f"{self._settings.local_llm_base_url.rstrip('/')}/api/generate",
            json=payload,
            stream=True,
            timeout=self._settings.local_llm_timeout_seconds,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                delta = str(data.get("response") or "")
                if delta:
                    yield delta
                if data.get("done"):
                    break

    def _should_send_chat_vision(self) -> bool:
        model = self._settings.local_llm_model.lower()
        return any(tag in model for tag in ("vl", "vision", "llava", "minicpm"))

    def _route_chat_intent(self, question: str) -> str | None:
        text = question.strip()
        lowered = text.lower()
        if lowered == "status":
            git_status = self._code_ops.git_status()
            summary = self._session_summary()
            return f"{summary}\n{git_status}".strip()
        if lowered.startswith(("search ", "find ", "look up ", "what is ")):
            query = text.split(" ", 1)[1] if " " in text else ""
            return self._browser_ops.search_web(query)
        if lowered.startswith("open "):
            target = text.split(" ", 1)[1] if " " in text else ""
            return self._browser_ops.open_url(target)
        if lowered.startswith(("read ", "show ", "what is in ")):
            path = text.split(" ", 1)[1] if " " in text else ""
            return self._code_ops.read_file(path)
        return None

    def _session_summary(self) -> str:
        now = time.localtime()
        day_start = time.mktime(
            (now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, now.tm_wday, now.tm_yday, now.tm_isdst)
        )
        count = self._memory_db.interaction_count_since(day_start)
        goal = self._goal_engine.summary()
        health = self._health.status_summary() if hasattr(self, "_health") else ""
        summary = f"Today has {count} interactions. Goal: {goal}."
        return f"{summary}\n{health}".strip()

    def _handle_goal_capture(self, text: str) -> str | None:
        result = self._session_lifecycle.maybe_capture_goal(text)
        if result is None:
            return None
        if result.accepted:
            self._goal_engine._current_goal = text.strip()
        return result.response

    def _refresh_health(self) -> None:
        if self._settings.local_llm_provider == "ollama":
            self._health.ping_local_llm(self._settings.local_llm_base_url)
        gemini_ok = bool(self._settings.gemini_api_key.strip())
        self._health.set_gemini_state(gemini_ok)
        fallback = self._health.evaluate_fallbacks()
        self._safe_mode = bool(fallback.get("safe_mode"))
        if self._safe_mode and not self._safe_mode_notified:
            if self._system_ops:
                self._system_ops.show_notification(
                    "ScreenSense",
                    "both local and cloud models offline. safe mode active.",
                )
            self._safe_mode_notified = True
        if not self._safe_mode:
            self._safe_mode_notified = False
        mode = str(fallback.get("reasoning_mode") or "").strip()
        disable_vision = bool(fallback.get("disable_vision"))
        if mode in {"gemini", "local", "hybrid"} and mode != self._settings.reasoning_mode:
            self._settings.reasoning_mode = mode  # dynamic override
            self._inference = self._build_inference_client()
        if disable_vision:
            self._settings.local_llm_use_vision = False

    def _kill_local_llm(self) -> str:
        self._health.kill_local_llm()
        if self._settings.gemini_api_key.strip():
            self._settings.reasoning_mode = "gemini"
            self._inference = self._build_inference_client()
        return "local model killed. cloud fallback active."

    @staticmethod
    def _has_real_chat_context(app_context: dict[str, object]) -> bool:
        ui_text = str(app_context.get("ui_text_excerpt") or "").strip()
        if ui_text:
            return True
        ui_ctx = app_context.get("ui_context_text")
        if ui_ctx and str(ui_ctx).strip():
            return True
        ui_json = app_context.get("ui_context_json")
        if isinstance(ui_json, dict) and ui_json:
            return True
        return False

    def _broadcast_state(self, status: str, text: str = "") -> None:
        cleaned_text = clean_response_proactive(text) if text else ""
        self._ipc_state = {"status": status, "text": cleaned_text}
        if not hasattr(self, "_ipc_clients") or not self._ipc_clients:
            return
            
        import websockets
        
        async def broadcast():
            message = json.dumps(self._ipc_state)
            websockets.broadcast(self._ipc_clients, message)
            
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast())
        except RuntimeError:
            pass # No running loop in this thread, that's fine for simple broadcast. We'll use a hack to push.
        
        # Since we are in a synchronous thread, we need to push to the asyncio loop.
        # For simplicity, we just format the message.
        message = json.dumps(self._ipc_state)
        for client in list(self._ipc_clients):
            try:
                # In python websockets, send() is an awaitable. We fire and forget using asyncio.run_coroutine_threadsafe if we had the loop, 
                # but to avoid complex loop passing, we'll try to find the loop of the client.
                loop = client.loop
                asyncio.run_coroutine_threadsafe(client.send(message), loop)
            except Exception:
                pass

    def _whisper_approval(self, message: str) -> None:
        self._broadcast_state("Approval", text=message)

    def _approve_file_write(self, path: str, action_type: str) -> bool:
        preview = f"{action_type} {path}"
        return self._action_gate.request_approval(lambda: True, preview, "high")

    def _extract_error_text(self, ui_context: dict[str, object]) -> str:
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

    def _maybe_update_stackoverflow_hint(self, ui_context: dict[str, object]) -> str:
        if not self._browser_ops:
            return ""
        error_text = self._extract_error_text(ui_context)
        if not error_text:
            return ""
        now = time.time()
        if error_text == self._last_stackoverflow_text and (now - self._last_stackoverflow_ts) < 120:
            return self._stackoverflow_hint
        hint = self._browser_ops.search_stackoverflow(error_text)
        self._last_stackoverflow_text = error_text
        self._last_stackoverflow_ts = now
        self._stackoverflow_hint = hint
        return hint


def _voice_compose(text: str, decision: VisionDecision) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = re.sub(
        r"^(sure|hello|i notice|i detected|as an ai|great|certainly)[,\\s]+",
        "",
        cleaned,
        flags=re.I,
    )
    words = cleaned.split()
    if len(words) > 15:
        cleaned = " ".join(words[:15]).rstrip()
    if decision.can_fix or decision.proposed_action:
        if not cleaned.endswith("?"):
            cleaned = cleaned.rstrip(".") + "?"
    else:
        if cleaned.endswith("?"):
            cleaned = cleaned.rstrip("?") + "."
    return cleaned
