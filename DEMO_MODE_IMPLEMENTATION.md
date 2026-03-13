# Demo Mode Implementation Summary

## What Was Built

A complete demo mode system that bypasses the entire inference pipeline with hardcoded responses triggered by keywords.

## Files Created

1. **src/screensense/demo_responses.py** (200 lines)
   - Dictionary of 60+ trigger keywords → responses
   - Covers: development, browsers, terminals, productivity, learning, communication, design, data, databases, AI/ML, testing, DevOps
   - `get_demo_response()` - Main trigger checking function
   - `add_demo_response()` - Runtime response addition
   - `remove_demo_response()` - Runtime response removal
   - `list_demo_triggers()` - List all triggers

2. **DEMO_MODE.md** (Documentation)
   - Complete usage guide
   - Trigger keyword reference
   - Comparison table: Demo vs Normal mode
   - Use cases and best practices
   - Troubleshooting guide

3. **test_demo_mode.py** (Test script)
   - Test window title triggers
   - Test clipboard triggers
   - List all available triggers

## Files Modified

1. **.env**
   - Added `DEMO_MODE=false` (disabled by default)

2. **src/screensense/config.py**
   - Added `demo_mode: bool = False` field
   - Added parsing in `load_settings()`

3. **src/screensense/core/coordinator.py**
   - Imported `get_demo_response`
   - Added demo mode intercept at start of `_tick()` method
   - Checks window title + clipboard for triggers
   - Speaks response immediately if match found
   - Logs demo trigger events
   - Returns early, skipping entire inference pipeline


## How It Works

### Flow Diagram
```
┌─────────────────────────────────────────────────┐
│ coordinator._tick() called                      │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ DEMO_MODE=true?│
         └────┬───────┬───┘
              │       │
           NO │       │ YES
              │       │
              │       ▼
              │  ┌─────────────────────────┐
              │  │ Get window title        │
              │  │ Get clipboard content   │
              │  └──────────┬──────────────┘
              │             │
              │             ▼
              │  ┌─────────────────────────┐
              │  │ get_demo_response()     │
              │  │ Check for keyword match │
              │  └──────────┬──────────────┘
              │             │
              │       ┌─────┴─────┐
              │       │           │
              │    MATCH       NO MATCH
              │       │           │
              │       ▼           │
              │  ┌─────────────┐ │
              │  │ Speak now   │ │
              │  │ Log event   │ │
              │  │ Return      │ │
              │  └─────────────┘ │
              │                  │
              ▼                  ▼
    ┌──────────────────────────────┐
    │ Continue normal inference    │
    │ (LLM, Vision, UIA, etc.)     │
    └──────────────────────────────┘
```

### Code Flow

1. **Coordinator Loop** (`_tick()`)
   ```python
   if self._settings.demo_mode:
       window_title = ui_context.get("window_title", "")
       clipboard_content = pyperclip.paste()
       
       demo_response = get_demo_response(window_title, clipboard_content)
       if demo_response:
           self._voice.speak_event(demo_response, context="Demo", confidence=1.0)
           self._audit.log("demo_mode_triggered", {...})
           return  # Skip inference
   ```

2. **Trigger Matching** (`demo_responses.py`)
   ```python
   def get_demo_response(window_title, clipboard_content):
       title_lower = window_title.lower()
       
       # Check window title
       for keyword, response in DEMO_RESPONSES.items():
           if keyword in title_lower:
               return response
       
       # Check clipboard
       if clipboard_content:
           clipboard_lower = clipboard_content.strip().lower()
           if clipboard_lower in CLIPBOARD_TRIGGERS:
               return CLIPBOARD_TRIGGERS[clipboard_lower]
       
       return None
   ```

## Example Triggers

### Development Tools
```python
"visual studio code": "VS Code is open. I'm monitoring for errors and can help with code suggestions when you need them.",
"error": "I notice an error on screen. Would you like me to analyze it and suggest a fix?",
"python": "Python code detected. I'm monitoring for errors and ready to help with any questions.",
```

### Browsers
```python
"stack overflow": "I see you're on Stack Overflow. Looking for solutions to a coding problem? I can help explain any code snippets you find.",
"github": "You're browsing GitHub. Need help understanding this repository structure or want me to explain any code?",
```

### Terminals
```python
"powershell": "PowerShell terminal active. Running commands? I can help with syntax or explain what commands do.",
"git": "Git command detected. Need help with version control or resolving merge conflicts?",
```

## Usage Examples

### Example 1: Demo Presentation
```bash
# Setup
echo "DEMO_MODE=true" >> .env
python -m screensense.app

# Demo flow
1. Open VS Code → "VS Code is open. I'm monitoring for errors..."
2. Open Stack Overflow → "I see you're on Stack Overflow..."
3. Open PowerShell → "PowerShell terminal active..."
4. Copy "help" → "I'm ARIA, your desktop AI assistant..."
```

### Example 2: Voice Testing
```bash
# Test voice without waiting for LLM
DEMO_MODE=true python -m screensense.app

# Open any window with "python" in title
# Instant voice response
```

### Example 3: Custom Triggers
```python
# Add custom trigger at runtime
from screensense.demo_responses import add_demo_response

add_demo_response(
    "my app",
    "I see you're using My App. Need help with features?"
)
```

## Performance

| Metric | Normal Mode | Demo Mode |
|--------|-------------|-----------|
| Response Time | 2-5 seconds | <100ms |
| CPU Usage | High (LLM) | Minimal |
| Memory | ~2GB (models) | ~50MB |
| Network | API calls | None |
| Accuracy | Context-aware | Fixed |

## Testing

Run test script:
```bash
python test_demo_mode.py
```

Expected output:
```
Testing Window Title Triggers:
--------------------------------------------------
✓ 'Visual Studio Code - main.py' → Triggered
  Response: VS Code is open. I'm monitoring for errors...

✓ 'Stack Overflow - Python Questions' → Triggered
  Response: I see you're on Stack Overflow. Looking for solutions?...

✗ 'Random Window' → No trigger

Testing Clipboard Triggers:
--------------------------------------------------
✓ Clipboard: 'help' → Triggered
  Response: I'm ARIA, your desktop AI assistant...

All Available Triggers:
--------------------------------------------------
Total: 60+ triggers
```

## Audit Logging

Demo triggers are logged to `runtime/audit.log.jsonl`:
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "event": "demo_mode_triggered",
  "data": {
    "window_title": "Visual Studio Code - main.py",
    "clipboard_preview": null,
    "response": "VS Code is open. I'm monitoring for errors...",
    "loop_count": 42
  }
}
```

## Configuration

### Enable Demo Mode
```bash
# .env
DEMO_MODE=true
```

### Disable Demo Mode (Default)
```bash
# .env
DEMO_MODE=false
```

### With Other Settings
```bash
# .env
DEMO_MODE=true
ENABLE_TTS=true
VOICE_PROVIDER=edge_tts
CAPTURE_INTERVAL_SECONDS=2
```

## Advantages

1. **Instant Response** - No LLM latency
2. **Predictable** - Same trigger = same response
3. **Offline** - No API/model required
4. **Lightweight** - Minimal CPU/memory
5. **Reliable** - No inference errors
6. **Demo-Ready** - Perfect for presentations

## Limitations

1. **No Context** - Can't analyze actual screen content
2. **Fixed Responses** - No adaptation or learning
3. **Keyword Only** - Simple string matching
4. **No Intelligence** - No reasoning or problem-solving
5. **Manual Updates** - Must add triggers manually

## When to Use

✓ Live demos and presentations
✓ Voice/TTS testing
✓ Quick feedback during development
✓ Offline operation
✓ Debugging audio issues

✗ Production use
✗ Real assistance
✗ Context-aware help
✗ Learning/adaptation

## Future Enhancements

Possible improvements:
- Regex pattern matching
- Priority/ordering for overlapping triggers
- Time-based triggers (morning/evening greetings)
- User-specific trigger files
- Web UI for managing triggers
- Import/export trigger sets
- Trigger analytics (most used, etc.)
