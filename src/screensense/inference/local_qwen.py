from __future__ import annotations

import json
import re
import time
from collections import deque
from typing import Any

import numpy as np
import requests
from pydantic import ValidationError

from screensense.core.ui_context import UiContextExtractor
from screensense.inference.image_codec import encode_png_base64
from screensense.models import VisionDecision
from screensense.perception import (
    ContextAssembler,
    CrossModalComparator,
    OmniParserClient,
    PassiveContextCollector,
    SemanticDeduplicator,
    WindowMetadata,
    WindowsUIAAdapter,
)


LOCAL_PROMPT = """You are ARIA. Output ONLY valid JSON with ALL required fields. No markdown, no extra text.

REQUIRED JSON STRUCTURE (you MUST include ALL fields):
{
  "context": "string - what app/window (max 50 chars)",
  "should_interrupt": boolean,
  "confidence": number between 0.0 and 1.0,
  "message": "string - 2-3 descriptive sentences",
  "can_fix": boolean,
  "priority": "critical" OR "helpful" OR "silent",
  "domain": "code" OR "translate" OR "browse" OR "general",
  "proposed_action": "string or null"
}

CRITICAL RULES:
- Be descriptive and detailed in "message" field (2-3 sentences)
- Reference SPECIFIC facts from verified context
- Explain what you see and why it matters
- Provide actionable insights when possible
- If nothing genuinely useful: should_interrupt=false, confidence=0.0
- MUST include ALL 8 fields above
- Output ONLY JSON, nothing else

Examples:
Verified Context: VS Code, auth.py line 47, terminal shows "ImportError: requests"
{"context":"VS Code auth.py","should_interrupt":true,"confidence":0.86,"message":"I notice auth.py has an ImportError on line 47 - the requests module is missing. This is blocking your code execution. You should install it with 'pip install requests' to fix this issue.","can_fix":true,"priority":"helpful","domain":"code","proposed_action":null}

Verified Context: Chrome browser, Stack Overflow visible, no errors
{"context":"Chrome","should_interrupt":false,"confidence":0.55,"message":"You're browsing Stack Overflow in Chrome. Everything looks normal with no visible errors or issues that need attention.","can_fix":false,"priority":"silent","domain":"general","proposed_action":null}

Verified Context: Terminal shows "connection refused localhost:11434"
{"context":"Terminal","should_interrupt":true,"confidence":0.84,"message":"The terminal is showing a connection refused error for localhost:11434, which is Ollama's default port. This means Ollama isn't running. Start it with 'ollama run llama3.2:3b' to fix this.","can_fix":false,"priority":"critical","domain":"general","proposed_action":null}

VERIFIED CONTEXT (cross-verified by OmniParser + Windows UIA):
{verified_context}

User: {user_name}
Project: {project_name}
Goal: {session_goal}

Output JSON only:"""


class LocalQwenInferenceClient:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        use_vision: bool = True,
        ui_context_extractor: UiContextExtractor | None = None,
        enable_verified_perception: bool = True,
    ) -> None:
        self._provider = provider
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._use_vision = use_vision
        self._ui_context_extractor = ui_context_extractor
        self.last_source = "local_qwen"
        self._recent_messages: deque[str] = deque(maxlen=8)
        
        # Verified perception components
        self._enable_verified_perception = enable_verified_perception
        self._omniparser: OmniParserClient | None = None
        self._uia_adapter: WindowsUIAAdapter | None = None
        self._comparator: CrossModalComparator | None = None
        self._context_assembler: ContextAssembler | None = None
        self._passive_collector: PassiveContextCollector | None = None
        self._semantic_dedup: SemanticDeduplicator | None = None
        
        if self._enable_verified_perception:
            self._init_verified_perception()
    
    def _init_verified_perception(self) -> None:
        """Initialize verified perception components"""
        try:
            self._omniparser = OmniParserClient(device="cpu")
            self._uia_adapter = WindowsUIAAdapter(cache_ttl_seconds=0.5, max_depth=10)
            self._comparator = CrossModalComparator(position_tolerance=20)
            self._context_assembler = ContextAssembler(max_tokens=4000)
            self._passive_collector = PassiveContextCollector()
            self._semantic_dedup = SemanticDeduplicator(similarity_threshold=0.85)
            print("[LocalQwen] Verified perception initialized")
        except Exception as e:
            print(f"[LocalQwen] Failed to init verified perception: {e}")
            self._enable_verified_perception = False

    def analyze(
        self,
        frame_rgb: np.ndarray,
        app_context: dict[str, str | int | bool | None] | None = None,
    ) -> VisionDecision:
        context = dict(app_context or {})
        if self._ui_context_extractor is not None:
            context = self._ui_context_extractor.enrich(frame_rgb=frame_rgb, app_context=context)

        if self._provider != "ollama":
            return self._fallback_decision(context, reason="local_llm_provider_disabled")
        
        # Use verified perception if enabled
        verified_context_text = ""
        if self._enable_verified_perception and self._omniparser and self._uia_adapter:
            verified_context_text = self._get_verified_context(frame_rgb, context)
        
        # Build prompt with verified context
        filled_prompt = LOCAL_PROMPT.format(
            verified_context=verified_context_text or self._fallback_context_text(context),
            user_name=context.get("user_name", "User"),
            project_name=context.get("project_name", "Project"),
            session_goal=context.get("goal", context.get("session_goal", "none")),
        )
        
        payload = {
            "model": self._model,
            "prompt": filled_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 512},  # Increased for longer responses
        }
        
        # Don't send vision frame - OmniParser already handled vision
        # Only send if verified perception is disabled
        if not self._enable_verified_perception and self._should_send_vision_frame():
            payload["images"] = [encode_png_base64(frame_rgb[::2, ::2])]
        
        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            text = str(body.get("response") or "").strip()
            if not text:
                return self._fallback_decision(context, reason="empty_response")
            
            print(f"[LocalQwen] Raw LLM response: {text[:200]}")  # DEBUG
            
            data = self._extract_json(text)
            if not data:
                return self._fallback_decision(context, reason="invalid_json")
            
            print(f"[LocalQwen] Parsed JSON keys: {list(data.keys())}")  # DEBUG
            
            # Ensure all required fields exist
            required_fields = ["context", "should_interrupt", "confidence", "message", "can_fix", "priority", "domain", "proposed_action"]
            for field in required_fields:
                if field not in data:
                    print(f"[LocalQwen] Missing field '{field}', adding default")  # DEBUG
                    data[field] = self._get_default_value(field, context)
            
            try:
                decision = VisionDecision.model_validate(data)
            except (ValidationError, KeyError) as e:
                print(f"[LocalQwen] ❌ Validation error: {e}")
                print(f"[LocalQwen] Data keys: {list(data.keys())}")
                print(f"[LocalQwen] Full data: {json.dumps(data, indent=2)}")
                print(f"[LocalQwen] Raw LLM text: {text}")
                return self._fallback_decision(context, reason=f"validation_error: {type(e).__name__}")
            except Exception as e:
                print(f"[LocalQwen] ❌ Unexpected error: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return self._fallback_decision(context, reason=f"unexpected_error: {type(e).__name__}")
            
            if not decision.context.strip():
                return self._fallback_decision(context, reason="local_blank_context")
            
            # Enforce word limit (increased to 50 words for descriptive responses)
            decision = self._enforce_word_limit(decision, max_words=50)
            
            # Check semantic deduplication
            if self._semantic_dedup and decision.message.strip():
                if self._semantic_dedup.is_duplicate(decision.message):
                    # Duplicate detected - silence
                    decision.should_interrupt = False
                    decision.confidence = 0.0
                    decision.message = ""
                else:
                    # Add to history
                    self._semantic_dedup.add_to_history(decision.message)
            
            decision = self._normalize_decision(decision, context)
            if decision.message.strip():
                self._recent_messages.append(decision.message.strip().lower())
            return decision
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[LocalQwen] Request/JSON error: {e}")
            return self._fallback_decision(context, reason=f"local_llm_error: {e}")

    @staticmethod
    def _get_default_value(field: str, context: dict) -> Any:
        """Provide safe defaults for missing fields"""
        defaults = {
            "context": str(context.get("window_title", "Desktop"))[:50],
            "should_interrupt": False,
            "confidence": 0.3,
            "message": "Monitoring screen activity",
            "can_fix": False,
            "priority": "silent",
            "domain": "general",
            "proposed_action": "none",
        }
        return defaults.get(field, "")
    
    def _get_verified_context(self, frame_rgb: np.ndarray, context: dict) -> str:
        """Run verified perception pipeline and return context text"""
        try:
            # Get window metadata
            window_meta = WindowMetadata(
                process_name=str(context.get("process_name", "unknown")),
                window_title=str(context.get("window_title", "unknown")),
                pid=int(context.get("pid", 0)),
                timestamp=float(context.get("timestamp", time.time())),
            )
            
            # Run OmniParser detection
            omni_elements = []
            if self._omniparser:
                try:
                    omni_elements = self._omniparser.detect_elements(frame_rgb)
                    print(f"[LocalQwen] OmniParser detected {len(omni_elements)} elements")
                except Exception as e:
                    print(f"[LocalQwen] OmniParser detection failed: {e}")
            
            # Get UIA tree
            uia_elements = []
            if self._uia_adapter:
                try:
                    uia_elements = self._uia_adapter.get_accessibility_tree()
                    print(f"[LocalQwen] UIA extracted {len(uia_elements)} elements")
                except Exception as e:
                    print(f"[LocalQwen] UIA extraction failed: {e}")
            
            # Cross-modal comparison
            verified_elements = []
            if self._comparator:
                try:
                    verified_elements = self._comparator.compare_elements(omni_elements, uia_elements)
                    high_conf = sum(1 for e in verified_elements if e.confidence.value == "high")
                    low_conf = sum(1 for e in verified_elements if e.confidence.value == "low")
                    print(f"[LocalQwen] Verified {len(verified_elements)} elements (HIGH: {high_conf}, LOW: {low_conf})")
                except Exception as e:
                    print(f"[LocalQwen] Cross-modal comparison failed: {e}")
            
            # Collect passive signals
            passive_signals = None
            if self._passive_collector:
                try:
                    passive_signals = self._passive_collector.collect(window_meta)
                    print(f"[LocalQwen] Passive signals: clipboard={passive_signals.clipboard_content is not None}, url={passive_signals.browser_url is not None}")
                except Exception as e:
                    print(f"[LocalQwen] Passive signal collection failed: {e}")
                    # Create empty passive signals
                    from .passive_signals import PassiveSignals
                    passive_signals = PassiveSignals(
                        clipboard_content=None,
                        browser_url=None,
                        recent_files=[],
                        window_metadata=window_meta,
                        timestamp=time.time(),
                    )
            
            # Assemble context
            if self._context_assembler and passive_signals:
                try:
                    rich_context = self._context_assembler.assemble_context(
                        verified_elements=verified_elements,
                        passive_signals=passive_signals,
                        session_goal=str(context.get("goal", context.get("session_goal", ""))),
                        user_name=str(context.get("user_name", "")),
                        project_name=str(context.get("project_name", "")),
                    )
                    serialized = self._context_assembler.serialize_for_llm(rich_context)
                    print(f"[LocalQwen] Context assembled: {len(serialized)} chars")
                    return serialized
                except Exception as e:
                    print(f"[LocalQwen] Context assembly failed: {e}")
            
            return ""
        except Exception as e:
            print(f"[LocalQwen] Verified perception failed: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _fallback_context_text(self, context: dict) -> str:
        """Fallback context text when verified perception unavailable"""
        return f"""Active Window: {context.get('window_title', 'unknown')}
Process: {context.get('process_name', 'unknown')}
UI Text: {str(context.get('ui_text_excerpt', ''))[:200]}
"""
    
    def _enforce_word_limit(self, decision: VisionDecision, max_words: int) -> VisionDecision:
        """Enforce word limit on message field"""
        if not decision.message:
            return decision
        
        words = decision.message.split()
        if len(words) > max_words:
            decision.message = " ".join(words[:max_words])
        
        return decision

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        return {}

    @staticmethod
    def _fallback_decision(
        context: dict[str, str | int | bool | None],
        *,
        reason: str,
    ) -> VisionDecision:
        title = str(context.get("window_title") or "Desktop")
        title = re.sub(r"\s+", " ", title).strip()
        return VisionDecision(
            context=title[:50] or "Desktop",
            should_interrupt=False,
            confidence=0.25,
            message=f"Local reasoning unavailable ({reason}). Monitoring silently.",
            can_fix=False,
            priority="silent",
            domain="general",
        )

    def _normalize_decision(
        self,
        decision: VisionDecision,
        context: dict[str, str | int | bool | None],
    ) -> VisionDecision:
        message = re.sub(r"\s+", " ", decision.message.strip())
        message = _limit_sentences(message, max_sentences=2)
        lowered = message.lower()
        generic_patterns = (
            "stay focused",
            "keep coding",
            "more coding left",
            "more videos await",
            "great content ahead",
        )
        if not message or any(p in lowered for p in generic_patterns):
            app = str(context.get("window_title") or context.get("process_name") or "screen").strip()
            excerpt = str(context.get("ui_text_excerpt") or "").strip()
            clue = self._best_clue(excerpt)
            message = f"{app}: {clue}" if clue else f"{app}: notable screen change detected."

        # De-repeat if exact line was just used.
        if message.lower() in self._recent_messages:
            app = str(context.get("window_title") or "screen").strip()
            message = f"{message} Check {app} now."

        if len(message) > 180:
            message = message[:177].rstrip() + "..."
        decision.message = message
        return decision

    def _should_send_vision_frame(self) -> bool:
        if not self._use_vision:
            return False
        model = self._model.lower()
        return any(tag in model for tag in ("vl", "vision", "llava", "minicpm"))

    @staticmethod
    def _best_clue(excerpt: str) -> str:
        cleaned = re.sub(r"\s+", " ", excerpt).strip()
        if not cleaned:
            return ""
        keywords = (
            "error",
            "exception",
            "traceback",
            "failed",
            "failure",
            "warning",
            "warn",
            "todo",
            "fixme",
            "line ",
            "undefined",
            "null",
            "stack",
            "denied",
            "forbidden",
            "timeout",
        )
        lowered = cleaned.lower()
        for key in keywords:
            idx = lowered.find(key)
            if idx >= 0:
                start = max(0, idx - 18)
                end = min(len(cleaned), idx + 62)
                return cleaned[start:end].strip()
        return cleaned[:96]


def _limit_sentences(text: str, *, max_sentences: int) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    limited = " ".join(parts[:max_sentences]).strip()
    return limited
