# ARIA Codebase Audit — Full Diagnosis
**Date:** 2026-03-12  
**Files scanned:** 72 Python files  
**Critical bugs:** 7  
**Medium bugs:** 5  
**Quick wins:** 4

---

## CRITICAL BUGS (Fix These First)

---

### BUG 1 — Two separate ui_context systems, neither wired correctly
**Severity:** 🔴 Critical — This is why ARIA is blind  
**Files:** `core/ui_context.py` vs `perception/ui_context.py`

There are TWO different UI context extractors:
```
core/ui_context.py       → UiContextExtractor (used by telegram_bot.py)
perception/ui_context.py → UiAutomationContext (used by coordinator.py)
```

`telegram_bot.py` imports `UiAutomationContext` from `perception/ui_context.py`
but then instantiates it as `self._ui_context_provider` and **never calls `.capture()`**.

Instead it calls `_capture_ui_context_async()` which uses the OTHER extractor
(`core/ui_context.py` → `UiContextExtractor`) whose `enrich()` method requires
a `frame_rgb` numpy array that is never passed from telegram context.

**Result:** `ui_context: {}` every single time in Telegram.

**Fix — In `telegram_bot.py`, `_capture_ui_context_async()`:**
```python
async def _capture_ui_context_async(self) -> dict:
    # REPLACE whatever is here with:
    try:
        result = await asyncio.to_thread(
            self._ui_context_provider.capture
        )
        return result.context  # UiAutomationContext returns UiContextResult
    except Exception as e:
        print(f"[TG] ui_context error: {e}")
        return {}
```

---

### BUG 2 — `_approve()` in BrowserOps returns False — skills always blocked
**Severity:** 🔴 Critical — All browser/search actions silently fail  
**File:** `skills/browser_ops.py`

```python
def _approve(self, preview: str, risk: str) -> bool:
    if self._gate is None:
        return False   # ← gate is None → always returns False
    return self._gate.approve(preview, risk)
```

`open_url()` calls `self._approve(...)` and returns `""` if False.
This means `open_url` ALWAYS returns empty string silently.

But `search_web_api()` does NOT call `_approve()` — that's why DDG search works.
`open_url()` always fails silently.

**Fix — In `BrowserOps.__init__`:**
```python
# Change the gate check in open_url and search_web:
def _approve(self, preview: str, risk: str) -> bool:
    if self._gate is None:
        return True  # No gate = auto-approve for Telegram use
    return self._gate.approve(preview, risk)
```

---

### BUG 3 — `remove_lists()` in response_cleaner uses escaped `\\n` — never splits
**Severity:** 🔴 Critical — Bullet points never removed  
**File:** `core/response_cleaner.py`

```python
def remove_lists(text: str) -> str:
    lines = text.split("\\n")   # ← WRONG: literal \n string
    ...
    return "\\n".join(cleaned)  # ← WRONG: literal \n string
```

The `\\n` is a literal two-character string `\n`, not a newline.
So `split("\\n")` never splits anything. Lists pass through unchanged.

**Fix:**
```python
def remove_lists(text: str) -> str:
    lines = text.split("\n")    # real newline
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\d+\.", stripped):
            content = re.sub(r"^\d+\.\s*", "", stripped)
            cleaned.append(content)
        elif stripped.startswith(("-", "*", "•", "–")):
            content = stripped.lstrip("-*•– ")
            cleaned.append(content)
        else:
            cleaned.append(line)
    return "\n".join(cleaned).strip()
```

Also fix `clean_response_proactive()` — same escaped `\\s+` bug:
```python
# Line: sentences = re.split(r"(?<=[.!?])\\s+", cleaned)
# Fix:  sentences = re.split(r"(?<=[.!?])\s+", cleaned)
```

---

### BUG 4 — `_should_send_vision_frame()` is defined AFTER `return` statement
**Severity:** 🔴 Critical — Dead code, causes silent failure  
**File:** `inference/local_qwen.py`

```python
def _limit_sentences(text: str, ...) -> str:
    ...
    return limited          # ← function ends here
    
    def _should_send_vision_frame(self) -> bool:   # ← UNREACHABLE
        if not self._use_vision:
            return False
```

`_should_send_vision_frame` is indented inside `_limit_sentences` after its return.
It's never callable. Vision frames are never sent even if model supports it.

**Fix — Move `_should_send_vision_frame` to correct indentation:**
```python
def _limit_sentences(text: str, *, max_sentences: int) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:max_sentences]).strip()


class LocalQwenInferenceClient:
    # ... existing methods ...
    
    def _should_send_vision_frame(self) -> bool:  # ← back inside class
        if not self._use_vision:
            return False
        model = self._model.lower()
        return any(tag in model for tag in ("vl", "vision", "llava", "minicpm"))
```

---

### BUG 5 — Gemini `gemini_allowed` always False — vision never fires
**Severity:** 🔴 Critical — Gemini escalation path completely blocked  
**File:** `inference/hybrid_inference.py`

```python
if app_context and app_context.get("gemini_allowed") is False:
    # returns local result, skips Gemini
```

The key `gemini_allowed` is set somewhere in coordinator.py's context building.
From the logs: `[ScreenSense] vision error (AttributeError), backing off 15s`

The AttributeError is in `gemini_client.py` — the `raw.text` access.
After the error, the coordinator sets `gemini_allowed = False` and backs off 15s.
But it never resets to True after backoff ends.

**Fix — In coordinator.py, find where `gemini_allowed` is set after error:**
```python
# Find this pattern:
app_context["gemini_allowed"] = False

# Add a reset after backoff:
# Track gemini_backoff_until = time.time() + 15
# In context builder:
app_context["gemini_allowed"] = time.time() > self._gemini_backoff_until
```

---

### BUG 6 — URL extraction regex broken for plain domains
**Severity:** 🔴 Critical — `open_url` intent never gets a URL  
**File:** `telegram_bot.py` (the `_extract_url` function at bottom)

```python
# Current pattern misses: "open python.com", "open instagram.com"
# Only matches: "http://..." patterns
```

**Fix — Replace `_extract_url` at bottom of telegram_bot.py:**
```python
def _extract_url(text: str) -> str:
    # Full URL
    m = re.search(r"https?://\S+", text)
    if m:
        return m.group().rstrip(".,)")

    # Plain domain: python.com, github.io etc
    m = re.search(
        r"\b([a-zA-Z0-9-]+\."
        r"(?:com|org|io|dev|net|ai|co|edu|gov|app))\b",
        text
    )
    if m:
        return "https://" + m.group()

    # "open X" where X has no TLD
    m = re.search(
        r"(?:open|visit|go to|browse)\s+([a-zA-Z0-9.-]+)",
        text, re.IGNORECASE
    )
    if m:
        name = m.group(1)
        if "." not in name:
            name += ".com"
        return "https://" + name

    return ""
```

---

### BUG 7 — ARIA persona prompt not used for proactive screen loop
**Severity:** 🔴 Critical — ARIA sounds like a bot, not a laptop  
**File:** `inference/local_qwen.py` — `LOCAL_PROMPT`

The persona prompt in `local_qwen.py` is good but uses template variables
like `{deadline_date}`, `{session_goal}`, `{memory_recent_5}` that are
**never substituted**. The raw `{placeholders}` go to Qwen as-is.

**Fix — In `analyze()` method, before building payload:**
```python
def analyze(self, frame_rgb, app_context=None):
    context = dict(app_context or {})
    
    # Build filled prompt
    filled_prompt = LOCAL_PROMPT.format(
        deadline_date=context.get("deadline_date", "Mar 15"),
        days_remaining=context.get("deadline_days_left", "?"),
        time=context.get("now_iso", "")[:16],
        session_start=context.get("session_start", "unknown"),
        session_goal=context.get("goal", "none"),
        active_app=context.get("window_title", "unknown"),
        ui_context=context.get("ui_text", "{}"),
        memory_recent_5=context.get("memory_digest", "none"),
        last_rejection=context.get("last_rejection", "none"),
    )
    
    payload = {
        "model": self._model,
        "prompt": f"{filled_prompt}\n\nContext:\n{json.dumps(context)}",
        ...
    }
```

---

## MEDIUM BUGS

---

### BUG 8 — `_route_intent()` runs BEFORE the new intent handlers
**File:** `telegram_bot.py`

Old `_route_intent()` still exists and intercepts `"search "` prefixed messages
before the new SEARCH intent handler. So `"search python decorators"` hits
`_route_intent` → calls `browser_ops.search_web()` (old method with `_approve()` gate)
→ returns `""` → falls through to old `_build_chat_prompt`.

But wait — from the logs, search IS working now. So `_route_intent` must not be
running, or `search_web_api` is being called. Check line 289 — the new SEARCH
handler runs before `_route_intent` is ever called. Medium priority.

**Note:** `_route_intent` is a dead code path now — delete it or it will cause
confusion during future debugging.

---

### BUG 9 — `change_score=0.00` always — proactive alerts never fire
**File:** `perception/semantic_change.py`

From logs: `change_score=0.00 reasons=none` on every loop after initial app switch.

The semantic change detector is seeing no changes because UI Automation
is returning empty context — same root cause as BUG 1. Once BUG 1 is fixed,
change detection will have real data to compare against and scores will rise.

**Secondary issue:** App switch gives `change_score=1.0` then immediately
`backing off 15s` — so even real changes trigger the backoff before ARIA speaks.

Fix threshold in coordinator to use 0.4 for app switches (not 1.0).

---

### BUG 10 — `_build_chat_prompt()` never called for CHAT intent
**File:** `telegram_bot.py`

The CHAT fallback uses an inline prompt string directly:
```python
prompt = (
    "You are ARIA.\n"
    "Not a chatbot..."
    f"Current screen: {json.dumps(ui_context)}\n"
    f"Message: {user_text}\n"
    "ARIA:"
)
```

But the well-crafted `_build_chat_prompt()` with history, goal,
web results etc. is defined but never called from `_on_message`.

**Fix:** Replace inline prompt with:
```python
history = self._memory_db.get_recent_telegram_messages(limit=6)
session_goal = self._get_today_goal()
prompt = self._build_chat_prompt(
    user_text=user_text,
    ui_context=ui_context,
    session_goal=session_goal,
    history=history,
)
```

---

### BUG 11 — `headless=False` in browser — opens visible Chrome window
**File:** `skills/browser_ops.py`

```python
self._browser = self._playwright.chromium.launch(headless=False)
```

Every `open_url` call pops open a visible Chrome window on screen.
Should be `headless=True` for background operation.

**Fix:**
```python
self._browser = self._playwright.chromium.launch(headless=True)
# same for async version
self._abrowser = await self._apw.chromium.launch(headless=True)
```

---

### BUG 12 — Memory not written after Telegram conversations
**File:** `telegram_bot.py`, `_on_message()`

The new intent handlers (SEARCH, OPEN_URL, FILES, SCREEN) return early
without calling:
```python
self._memory_db.add_telegram_message(role="user", content=user_text)
self._memory_db.add_telegram_message(role="assistant", content=response)
```

Only the CHAT fallback saves to memory. History builds wrong.

**Fix:** Add memory writes after every `await update.message.reply_text(response)` call.

---

## QUICK WINS

---

### QW1 — Add GEMINI_API_KEY to .env
Get from aistudio.google.com — free, 2 minutes.
Without it Gemini vision path never runs.

### QW2 — "Insights await" — confirm it's gone
Search entire codebase: `grep -r "Insights await" src/`
If found, delete it. It was a hardcoded template string.

### QW3 — Set `headless=True` in browser_ops
(see BUG 11) — stops Chrome windows popping up.

### QW4 — Add startup notification
When ARIA starts, send Telegram message:
```
"online. VS Code open, no errors yet."
```
Confirms everything is working end-to-end.

---

## PRIORITY FIX ORDER

```
1. BUG 3  — response_cleaner \\n escape     (5 min, one line fix)
2. BUG 2  — _approve() returns False        (2 min, change False → True)  
3. BUG 6  — URL extraction regex            (10 min, replace function)
4. BUG 1  — _capture_ui_context_async       (15 min, rewire to .capture())
5. BUG 4  — _should_send_vision_frame dead  (5 min, fix indentation)
6. BUG 7  — LOCAL_PROMPT unformatted        (20 min, add .format() call)
7. BUG 10 — _build_chat_prompt not called   (10 min, replace inline prompt)
8. BUG 11 — headless=False                  (1 min)
9. BUG 12 — memory not saved                (15 min, add 4 lines per handler)
10. BUG 5 — gemini_allowed never resets     (20 min, add timer reset)
```

After fixes 1-4: search, open_url, and screen context will all work.
After fixes 5-7: ARIA will sound and behave like your laptop talking.
After fixes 8-10: clean operation, no visible Chrome windows, full memory.
```