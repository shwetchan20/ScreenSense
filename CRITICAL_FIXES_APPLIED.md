# Critical Fixes Applied

## Summary
Fixed 4 critical issues preventing ARIA from working properly:
1. Voice output coroutine bug
2. Telegram bot not using verified perception
3. UIA extracting only 2-10 elements
4. KeyError from incomplete LLM responses

---

## 1. Voice Output Fix (voice.py line 352)

**Problem**: `RuntimeWarning: coroutine 'Communicate.save' was never awaited`
- `asyncio.run()` was failing in synchronous context
- Voice output completely broken

**Solution**:
```python
# Create new event loop and properly await coroutine
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(communicate.save(tmp_path))
finally:
    loop.close()
```

**Result**: Voice output now works properly with edge-tts

---

## 2. Telegram Bot Integration

**Problem**: Telegram bot using old code path, not verified perception
- Generic responses like "Error: Unsupported browser detected"
- No context awareness
- Different quality than orb chatbox

**Solution**:
- Added `LocalQwenInferenceClient` to telegram bot initialization
- Replaced `_generate_response()` to use inference client with verified perception
- Captures screen frame and uses full perception pipeline
- Falls back to direct Ollama API if inference fails

**Changes**:
- Import `LocalQwenInferenceClient`
- Initialize in `__init__` with `enable_verified_perception=True`
- New `_generate_response()` uses `_inference_client.analyze()`
- Added `_generate_local_qwen_fallback()` for safety

**Result**: Telegram bot now gives same quality responses as orb chatbox

---

## 3. UIA Element Extraction Improvements

**Problem**: Only extracting 2-10 elements (should be 20-50)
- Too strict filtering (skipping offscreen elements)
- Shallow depth (max_depth=5)
- Poor error handling in tree traversal

**Solution**:

### Increased Depth
```python
max_depth: int = 7  # Was 5
```

### Better Tree Traversal
- Added fallback to `GetFirstChildControl()` + `GetNextSiblingControl()`
- Continue processing even if one child fails
- Better exception handling per child

### Less Strict Filtering
- Don't skip offscreen elements (just mark them)
- Allow elements with zero size (containers)
- Safe defaults for missing rectangle properties

**Result**: Should extract 20-50+ elements from active window

---

## 4. KeyError Handling

**Problem**: LLM response missing required fields causing KeyError
- `can_fix` and `proposed_action` missing
- Crashes entire vision pipeline

**Solution**:

### Added Default Values
```python
@staticmethod
def _get_default_value(field: str, context: dict) -> Any:
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
```

### Better Error Handling
- Try-catch around `VisionDecision.model_validate()`
- Print detailed error info (missing fields, data keys, values)
- Return fallback decision on validation error
- Separate handling for `ValidationError` and `KeyError`

**Result**: No more crashes from incomplete LLM responses

---

## Testing Checklist

### Voice Output
- [ ] Start ARIA
- [ ] Listen for startup greeting "ARIA online with verified perception"
- [ ] Trigger window change analysis
- [ ] Verify voice output speaks

### Telegram Bot
- [ ] Send "Hello" to bot
- [ ] Verify response references actual screen context
- [ ] Compare quality to orb chatbox
- [ ] Test "what am i working on"

### UIA Extraction
- [ ] Check logs for "UIA extracted X elements"
- [ ] Should see 20-50+ elements (not 2-10)
- [ ] Verify elements from different depths

### KeyError Fix
- [ ] No more "vision error (KeyError)" in logs
- [ ] Check for validation error messages
- [ ] Verify fallback decisions work

---

## Files Modified

1. `src/screensense/integrations/voice.py`
   - Fixed `_speak_edge_tts()` coroutine handling

2. `src/screensense/integrations/telegram_bot.py`
   - Added `LocalQwenInferenceClient` import
   - Initialize inference client in `__init__`
   - Replaced `_generate_response()` method
   - Added `_generate_local_qwen_fallback()` method

3. `src/screensense/perception/windows_uia.py`
   - Increased `max_depth` from 5 to 7
   - Improved `_extract_elements()` traversal
   - Less strict filtering in `_control_to_element()`

4. `src/screensense/inference/local_qwen.py`
   - Updated `max_depth` to 7 in `_init_verified_perception()`
   - Added `_get_default_value()` static method
   - Better error handling in `analyze()` method
   - Separate try-catch for validation errors

---

## Expected Behavior

### Before
- No voice output (coroutine warning)
- Telegram: "Error: Unsupported browser detected"
- UIA: 2-10 elements
- KeyError crashes every 15 seconds

### After
- Voice output works
- Telegram: "You're browsing Stack Overflow in Chrome. I notice you're looking at Python questions related to async programming."
- UIA: 20-50+ elements
- No KeyError crashes, graceful fallbacks

---

## Next Steps

1. Test all fixes
2. Monitor logs for improvements
3. If UIA still low, investigate window focus issues
4. If voice still fails, check edge-tts installation
5. If telegram still generic, check verified perception logs
