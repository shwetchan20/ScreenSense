# ARIA Architecture

## 1. Purpose
ARIA (inside ScreenSense) is a **fully local, zero-API** desktop AI co-pilot designed to be:

- always-on while the computer is on
- selective in interruptions (high signal, low noise)
- safe by default (human-in-the-loop and verification)
- adaptive over time (persona and app-specific behavior learning)
- **hallucination-free** through verified perception

The system is not intended to be a chatbot window. It is intended to be a background executive layer over normal desktop work.

## Core Innovation: Verified Perception Layer

ARIA's key architectural innovation is **cross-modal verification** - running two independent perception systems simultaneously and only trusting facts both agree on:

1. **OmniParser** (Microsoft's open-source UI model) - detects interactive elements with bounding boxes
2. **Windows UI Automation** - ground truth from Windows accessibility tree
3. **Cross-modal Comparator** - verifies outputs, assigns confidence levels

Only HIGH confidence facts (both sources agree) proceed to reasoning. This eliminates hallucination at the source.

## 2. Design Principles

1. **Fully local, zero-API**
- All perception and reasoning happens on-device
- No cloud dependencies, no API quotas, no network required
- OmniParser, Qwen2.5, and sentence-transformers run locally

2. **Verified perception over blind trust**
- Cross-verify vision model (OmniParser) against ground truth (UIA)
- Only facts both sources agree on are HIGH confidence
- LLM reasons on verified facts, not raw screenshots

3. Safety over speed
- Every executable action goes through policy and verification
- Risky actions are confirmation-gated

4. Asynchronous responsiveness
- Screen loop must keep running even if model calls are slow/failing
- Inference is non-blocking and stale outputs are dropped

5. Observability
- Major decisions and outcomes are audited
- The system records why interruptions/actions were allowed or blocked

6. Adaptation
- Tone and interruption behavior adapt from user feedback over time

## 3. High-Level Architecture

**Verified Perception Layer** (NEW - Core Innovation)
- `perception/omniparser_client.py`: OmniParser model wrapper for UI element detection
- `perception/windows_uia.py`: Windows UI Automation adapter for ground truth
- `perception/cross_modal_comparator.py`: Cross-verifies OmniParser vs UIA outputs
- `perception/passive_signals.py`: Clipboard, browser URL, file watcher, window metadata

**Context Assembly Layer** (ENHANCED)
- `perception/context_assembler.py`: Combines verified facts + passive signals into rich context
- No raw screenshots sent to LLM - only verified text facts

**Reasoning Layer** (CHANGED - Fully Local)
- `inference/local_qwen.py`: Qwen2.5 7B text-only reasoning (no vision needed)
- `perception/semantic_dedup.py`: Embedding-based deduplication using sentence-transformers
- OmniParser handles vision, Qwen reasons on verified facts only

Coordination Layer
- `core/coordinator.py`: orchestrates loop, policies, speaking, actions
- `core/rate_guard.py`: request throttling (local only, no API limits)
- `core/circuit_breaker.py`: temporary stop after repeated vision failures
- `core/decision_freshness.py`: drop stale async results

Action Layer (ENHANCED)
- `agents/*`: domain planning (`code`, `browse`, `general`, etc.)
- `agents/base.py`: typed action model + `ActionStep`
- `core/action_policy.py`: mode/risk allow/deny
- `core/action_executor.py`: Action Runner v2 with OmniParser bounding box precision

Interaction Layer
- `integrations/voice.py`: multi-engine TTS stack (Edge TTS - Jenny Neural)
- `integrations/remote_approval.py`: remote approval + alerts (Telegram)
- Native-first direction: tray/overlay pending; web dashboard kept debug-only

Memory + Adaptation Layer
- `memory/store.py` and `memory/persistence.py`
- `core/persona.py`: persona adaptation by feedback
- `core/app_preferences.py`: app-specific interruption threshold adaptation

Audit + Persistence
- `core/audit_logger.py`
- `storage/sinks.py`: local JSONL / Firestore / dual sink abstraction

## 4. Runtime Flow

1. Capture frame and compute diff.
2. If below threshold, skip.
3. Collect window context and apply skip gates:
- focus mode
- app blocklist
- fast-path skip
- circuit breaker
- rate guard
- async in-flight guard
4. Submit async inference job (local/hybrid/gemini).
5. When result returns:
- drop if stale (age/app switched)
- score impact and interrupt policy
- if allowed: speak + plan action
- execute action if policy allows
- verify outcome and audit everything

## 5. Why Key Decisions Were Made

Async inference instead of blocking calls
- Why: blocking model calls caused loop stalls and poor responsiveness.
- Tradeoff: async can return outdated decisions.
- Mitigation: freshness guard (`stale_decision_*`).

Hybrid reasoning mode
- Why: local-only was not reliable enough for all multimodal cases.
- Tradeoff: occasional API dependence.
- Mitigation: explicit escalation reasons + configurable thresholds.

Impact scoring before interrupt policy
- Why: model `should_interrupt` alone was noisy.
- Tradeoff: can suppress useful messages if too strict.
- Mitigation: tunable threshold + aggressiveness modes.

Action Runner v2 with typed steps
- Why: hardcoded one-shot actions were too limited.
- Tradeoff: more complexity in action schema.
- Mitigation: backward compatibility with legacy action types.

Verification reason + attempts
- Why: binary verified/unverified was insufficient for trust and debugging.
- Tradeoff: larger audit payload.
- Benefit: explicit failure analytics and safer autonomy.

Persona and app adaptation
- Why: static behavior felt robotic and inconsistent with long-term usage.
- Tradeoff: adds state and profile persistence.
- Mitigation: bounded updates and simple interpretable profile fields.

## 6. Current Capabilities

Implemented:
- local/hybrid/gemini reasoning modes
- OCR context enrichment
- stale decision dropping
- impact + interrupt policy gating
- Action Runner v2 (multi-step support)
- per-action verification metadata
- persona learning
- app-specific adaptation
- remote approval/alerts (Telegram)
- multi-provider voice stack and fallback handling

## 7. Known Gaps

1. Planner sophistication
- Current planning is still relatively shallow; no full task-graph planner yet.

2. UI automation depth
- Step runner exists, but full robust UI Automation integrations (deep element targeting) are still limited.

3. Native desktop UI shell
- Tray + native overlay as primary control interface remains pending.

4. End-to-end mobile app control
- Telegram bridge exists; dedicated mobile app control plane is pending.

## 8. Configuration Surfaces (Most Important)

Reasoning:
- `REASONING_MODE`
- `LOCAL_LLM_*`
- `LOCAL_LLM_ESCALATE_CONFIDENCE_THRESHOLD`
- `HYBRID_FORCE_GEMINI_ON_CRITICAL`

Interrupt behavior:
- `IMPACT_SCORE_THRESHOLD`
- `VOICE_AGGRESSIVENESS`
- `INTERRUPT_COOLDOWN_SECONDS`
- `DEDUPE_WINDOW_SECONDS`

Safety:
- `PRODUCT_MODE`
- `ASK_BEFORE_ACT`
- `ACTION_ALLOWLIST`
- `AUTO_EXECUTE_MAX_RISK`

Reliability:
- `GEMINI_MIN_CALL_INTERVAL_SECONDS`
- `GEMINI_MAX_CALLS_PER_MINUTE`
- `VISION_*` circuit breaker settings
- `STALE_DECISION_*`

Adaptation:
- `PERSONA_LEARNING_ENABLED`
- `PERSONA_PROFILE_PATH`
- `APP_ADAPTATION_ENABLED`
- `APP_PROFILE_PATH`

## 9. How to Evolve Next (Recommended Sequence)

1. Planner v2 (task graph + step synthesis + success criteria)
2. Deeper UI Automation adapters (element-level operations)
3. Native tray + overlay runtime UX (web optional only)
4. Policy hardening for autonomous multi-step workflows

## 10. Summary

ARIA is currently in a strong "agent core" stage:
- robust loop
- meaningful safety controls
- adaptive behavior
- growing action runtime

It is no longer a simple observer, but it is not yet full autonomous desktop operations at scale. The architecture is intentionally set up to move there incrementally without sacrificing safety.
