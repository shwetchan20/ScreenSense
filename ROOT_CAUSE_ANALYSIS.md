# Root Cause Analysis - ARIA Not Working

## Executive Summary
ARIA has 3 critical bugs preventing it from working:
1. **KeyError** - LLM returns incomplete JSON (missing `proposed_action`)
2. **No Voice** - Voice code runs but doesn't trigger (interrupt brain blocks it)
3. **Telegram Hallucinating** - ScreenCapturer method name wrong + no actual screen capture

---

## Bug #1: KeyError - LLM Response Incomplete

### Root Cause
The LLM (llama3.2:3b) is NOT following the JSON schema. It returns:
```json
{
  "context": "...",
  "should_interrupt": false,
  "confidence": 0.55,
  "message": "...",
  "can_fix": false,
  "priority": "silent",
  "domain": "general"
  // MISSING: "proposed_action"
}
```

### Why Default Values Don't Work
The code adds defaults BEFORE validation:
```python
for field in required_fields:
    if field not in data:
        data[field] = self._get_default_value(field, context)

decision = VisionDecision.model_validate(data)  # Still fails!
```

**Problem**: `VisionDecision` model has:
```python
proposed_action: str | None = None  # This is OPTIONAL (can be None)
```

So Pydantic should NOT fail on missing `proposed_action`. The KeyError must be coming from somewhere else.

### Actual Root Cause
Looking at the logs more carefully:
```
[LocalQwen] Parsed JSON keys: ['context', 'should_interrupt', ...]
[ScreenSense] vision error (KeyError), backing off 15s
```

The KeyError is NOT from Pydantic validation. It's from the coordinator trying to access a field that doesn't exist in the decision object.

**Real culprit**: Somewhere in coordinator.py, the code accesses `decision.some_field` that doesn't exist.

### Fix
Need to find where KeyError is raised in coordinator and add proper error handling.

---

## Bug #2: No Voice Output

### Root Cause
Voice code runs successfully but ARIA never speaks. Looking at the flow:

1. `_tick()` → submits inference to background thread
2. `_poll_pending_inference()` → gets result
3. `_handle_decision_flow()` → decides whether to speak
4. **Interrupt brain blocks it** → `interrupt.allow_interrupt = False`

### The Interrupt Brain Logic
```python
interrupt = self._interrupt_brain.evaluate(
    decision=decision,
    confidence=decision.confidence,
    typing_seconds_since=typing_seconds,
    session_minutes=snapshot.session_minutes,
)

if not interrupt.allow_interrupt and not self._settings.demo_force_speak:
    # VOICE BLOCKED - returns without speaking
    return
```

### Why It's Blocking
From logs:
```
[LocalQwen] Verified 2 elements (HIGH: 0, LOW: 2)
[LocalQwen] Context assembled: 379 chars
```

Only 2 elements detected → minimal context → LLM returns:
```json
{
  "should_interrupt": false,  // ← This tells interrupt brain to block
  "confidence": 0.3,          // ← Low confidence
  "priority": "silent"        // ← Silent priority
}
```

The interrupt brain sees these signals and blocks the voice output.

### Why Verified Perception Fails
1. **OmniParser**: Detects 0 elements (no trained weights)
2. **UIA**: Extracts only 2 elements (should be 20-50)
3. **Cross-modal**: Only 2 LOW confidence elements
4. **Context**: Only 379 chars (not enough for LLM)

### The Voice Code Works
The edge-tts fix is correct. The voice.py code runs fine. The problem is it never gets called because interrupt brain blocks it.

### Fix Options
1. **Force speak mode**: Set `DEMO_FORCE_SPEAK=true` in .env
2. **Fix UIA extraction**: Get 20-50 elements instead of 2
3. **Lower interrupt threshold**: Make interrupt brain less strict
4. **Better context**: Fix verified perception to provide rich context

---

## Bug #3: Telegram Bot Hallucinating

### Root Cause #1: Wrong Method Name
```python
# telegram_bot.py line ~950
capturer = self._get_capturer()
frame = capturer.capture()  # ← WRONG! Method doesn't exist
```

**Correct method**: `capture_rgb()`

```python
# capture.py
class ScreenCapturer:
    def capture_rgb(self) -> np.ndarray:  # ← Correct method name
        shot = self._sct.grab(self._monitor)
        bgra = np.array(shot, dtype=np.uint8)
        return bgra[:, :, :3][:, :, ::-1]
```

### Root Cause #2: No Screen Capture
Even if we fix the method name, telegram bot doesn't actually capture the screen. It falls back to the old code path which:
1. Builds a text prompt from UI context
2. Sends to Ollama /api/chat (NOT /api/generate)
3. Gets generic response based on text only
4. No vision, no verified perception

### Why It Hallucinates
The fallback prompt includes:
```python
context_str = " | ".join(context_parts)  # "App: python.exe | Window: python"
```

The LLM sees "python" and hallucinates about Python documentation because:
- No actual screen pixels
- No verified UI elements
- Just text context "python.exe"
- LLM fills in the blanks with training data

### Fix
1. Fix method name: `capture()` → `capture_rgb()`
2. Ensure inference client actually uses verified perception
3. Remove fallback to old code path (it's broken)

---

## Bug #4: UIA Only Extracting 2 Elements

### Root Cause
The UIA adapter is working but only finding 2 elements. Why?

### Hypothesis 1: Wrong Window
```python
window = auto.GetForegroundControl()
```

This gets the foreground window, but if ARIA's orb overlay is on top, it might be extracting from the orb instead of the actual app window.

### Hypothesis 2: Depth Too Shallow
Even with `max_depth=7`, if the window structure is:
```
Window (depth 0)
  └─ Pane (depth 1)
      └─ Pane (depth 2)
          └─ Pane (depth 3)
              └─ Pane (depth 4)
                  └─ Pane (depth 5)
                      └─ Pane (depth 6)
                          └─ [ACTUAL CONTENT] (depth 7) ← Can't reach!
```

### Hypothesis 3: Element Filtering Too Strict
The code filters out:
- Offscreen elements (fixed)
- Zero-size elements (fixed)
- Password fields (correct)

But maybe it's filtering too much.

### Fix
1. Skip orb window when extracting
2. Increase depth to 10
3. Add debug logging to see what's being filtered
4. Try different window selection strategy

---

## The Wiring Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Main Loop (coordinator.py _tick)                            │
│                                                              │
│ 1. Capture screen → ScreenCapturer.capture_rgb()           │
│ 2. Get UI context → UiAutomationContext.capture()          │
│ 3. Check if should infer (change score, fast path, etc)    │
│ 4. Submit to background thread → _analyze_with_source()    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Inference (local_qwen.py analyze)                           │
│                                                              │
│ 1. Get verified context:                                    │
│    - OmniParser.detect_elements() → 0 elements              │
│    - WindowsUIAAdapter.get_accessibility_tree() → 2 elem    │
│    - CrossModalComparator.compare() → 2 LOW conf           │
│    - ContextAssembler.assemble() → 379 chars               │
│                                                              │
│ 2. Build prompt with verified context                       │
│ 3. Call Ollama /api/generate with JSON format               │
│ 4. Parse response → VisionDecision                          │
│    ❌ Missing "proposed_action" → KeyError somewhere        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Decision Handling (coordinator.py _handle_decision_flow)    │
│                                                              │
│ 1. Interrupt brain evaluates:                               │
│    - should_interrupt: false                                │
│    - confidence: 0.3                                        │
│    - priority: silent                                       │
│    → interrupt.allow_interrupt = False                      │
│                                                              │
│ 2. ❌ BLOCKED - return without speaking                     │
│    Voice code never called!                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Telegram Bot (telegram_bot.py _generate_response)           │
│                                                              │
│ 1. Try to capture screen:                                   │
│    capturer.capture() ❌ AttributeError                     │
│                                                              │
│ 2. Fall back to old code path:                              │
│    - Build text prompt (no screen pixels)                   │
│    - Call Ollama /api/chat                                  │
│    - Get generic response                                   │
│    - LLM hallucinates based on "python.exe" text           │
└─────────────────────────────────────────────────────────────┘
```

---

## The Fixes (Priority Order)

### 1. Fix Telegram Bot Method Name (CRITICAL)
```python
# telegram_bot.py line ~950
frame = capturer.capture_rgb()  # Not capture()
```

### 2. Find and Fix KeyError Source (CRITICAL)
Search coordinator.py for where it accesses decision fields without checking if they exist.

### 3. Force Voice Output for Testing (IMMEDIATE)
```bash
# .env
DEMO_FORCE_SPEAK=true
```

This bypasses interrupt brain so we can test voice.

### 4. Fix UIA Extraction (HIGH PRIORITY)
```python
# windows_uia.py
max_depth: int = 10  # Increase from 7

# Skip orb window
if "python.exe" in window_title and "orb" in window_title.lower():
    # Get window behind orb
    pass
```

### 5. Add Detailed Logging (DEBUG)
```python
# local_qwen.py
print(f"[LocalQwen] Full LLM response: {text}")
print(f"[LocalQwen] Parsed data: {json.dumps(data, indent=2)}")

# coordinator.py
print(f"[Interrupt] allow={interrupt.allow_interrupt} reason={interrupt.reason}")
print(f"[Decision] interrupt={decision.should_interrupt} conf={decision.confidence}")
```

### 6. Improve Prompt (MEDIUM)
The prompt needs to be more explicit about JSON format:
```python
LOCAL_PROMPT = """You are ARIA. Output ONLY valid JSON with ALL required fields.

REQUIRED FIELDS (you MUST include ALL of these):
- context: string (what app/window)
- should_interrupt: boolean
- confidence: number 0.0-1.0
- message: string (2-3 sentences)
- can_fix: boolean
- priority: "critical" | "helpful" | "silent"
- domain: "code" | "translate" | "browse" | "general"
- proposed_action: string or null

...
"""
```

---

## Testing Plan

### Test 1: Telegram Bot
```bash
# Fix method name first
# Then test:
1. Send "Hello" to bot
2. Check logs for "TG] Inference client failed"
3. Should see screen capture working
4. Response should reference actual screen content
```

### Test 2: Voice Output
```bash
# Set DEMO_FORCE_SPEAK=true
# Start ARIA
# Should hear startup greeting immediately
# Change window → should speak after 6 seconds
```

### Test 3: UIA Extraction
```bash
# Add debug logging
# Check logs for element count
# Should see 20-50 elements, not 2
```

### Test 4: KeyError
```bash
# Add try-catch around decision field access
# Print full decision object
# Find which field is missing
```

---

## Expected Results After Fixes

### Before
```
[LocalQwen] UIA extracted 2 elements
[LocalQwen] Context assembled: 379 chars
[ScreenSense] vision error (KeyError), backing off 15s
[TG] Inference client failed: 'ScreenCapturer' object has no attribute 'capture'
[QWEN RAW]: page https://www.python.org | ... (hallucination)
```

### After
```
[LocalQwen] UIA extracted 47 elements
[LocalQwen] Context assembled: 2847 chars
[LocalQwen] Decision: should_interrupt=true, confidence=0.82
[Interrupt] allow=true reason=high_confidence_helpful
[Voice] Speaking: "You're editing requirements.md in VS Code..."
[TG] Screen captured: 1920x1080
[TG] Response: "I can see you're working on the requirements file..."
```
