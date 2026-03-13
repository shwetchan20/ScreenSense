# ARIA Demo Mode

## Overview
Demo mode bypasses the entire inference pipeline and uses hardcoded responses triggered by keywords in window titles or clipboard content. Perfect for demos, testing, or when you want instant predictable responses.

## Activation

Set in `.env`:
```
DEMO_MODE=true
```

## How It Works

1. Every loop, coordinator checks if `DEMO_MODE=true`
2. Extracts window title and clipboard content
3. Checks for trigger keywords (case-insensitive)
4. If match found, speaks hardcoded response immediately
5. Skips entire inference pipeline (no LLM, no vision, no UIA)

## Trigger Keywords

See `src/screensense/demo_responses.py` for full list. Examples:

### Development
- "visual studio code" → "VS Code is open. I'm monitoring for errors..."
- "error" → "I notice an error on screen. Would you like me to analyze it?"
- "python" → "Python code detected. I'm monitoring for errors..."

### Browser
- "stack overflow" → "I see you're on Stack Overflow. Looking for solutions?"
- "github" → "You're browsing GitHub. Need help understanding this repo?"
- "youtube" → "Watching a tutorial? Let me know if you need notes..."

### Terminal
- "powershell" → "PowerShell terminal active. Running commands?"
- "git" → "Git command detected. Need help with version control?"

### Productivity
- "notion" → "Notion is open. Taking notes or planning?"
- "todo" → "I see a TODO list. Want me to help prioritize?"

### Learning
- "tutorial" → "Following a tutorial? I can take notes for you..."
- "udemy" → "Udemy course detected. Learning something new?"

## Adding Custom Responses

### Runtime (Python)
```python
from screensense.demo_responses import add_demo_response

add_demo_response("my keyword", "My custom response")
```

### Permanent (Edit File)
Edit `src/screensense/demo_responses.py`:
```python
DEMO_RESPONSES: dict[str, str] = {
    "my keyword": "My custom response",
    # ... existing responses
}
```

## Clipboard Triggers

Special exact-match triggers for clipboard:
- "help" → Explains what ARIA does
- "aria" → "Yes? I'm here and monitoring..."
- "error" → "I'm checking for errors on your screen..."

## Demo vs Normal Mode

| Feature | Normal Mode | Demo Mode |
|---------|-------------|-----------|
| LLM Inference | ✓ | ✗ |
| Vision Analysis | ✓ | ✗ |
| UIA Extraction | ✓ | ✗ |
| OmniParser | ✓ | ✗ |
| Response Time | 2-5s | Instant |
| Context Aware | ✓ | ✗ |
| Predictable | ✗ | ✓ |

## Use Cases

1. **Live Demos**: Guaranteed responses for presentations
2. **Testing Voice**: Verify TTS without waiting for inference
3. **Debugging**: Isolate voice/audio issues from inference issues
4. **Quick Feedback**: Instant responses during development
5. **Offline Mode**: Works without Ollama/LLM running

## Logging

Demo mode triggers are logged:
```json
{
  "event": "demo_mode_triggered",
  "window_title": "Visual Studio Code",
  "clipboard_preview": "help",
  "response": "VS Code is open. I'm monitoring...",
  "loop_count": 42
}
```

## Limitations

- No actual screen analysis
- No context awareness
- No learning/adaptation
- Fixed responses only
- Keyword matching only (no semantic understanding)

## Best Practices

1. Use for demos/testing only
2. Keep responses short and clear
3. Add keywords for your specific use case
4. Test triggers before live demo
5. Disable for production use

## Example Demo Flow

1. Set `DEMO_MODE=true` in `.env`
2. Start ARIA: `python -m screensense.app`
3. Open VS Code → Instant: "VS Code is open..."
4. Open browser to Stack Overflow → Instant: "I see you're on Stack Overflow..."
5. Copy "help" to clipboard → Instant: "I'm ARIA, your desktop AI..."

## Troubleshooting

**No response?**
- Check window title contains trigger keyword
- Keywords are case-insensitive
- Check logs for "DEMO MODE: Triggered by..."

**Wrong response?**
- Multiple keywords may match
- First match wins (dictionary order)
- Check `DEMO_RESPONSES` in demo_responses.py

**Voice not working?**
- Demo mode uses same voice system
- Check `ENABLE_TTS=true` in .env
- Verify edge-tts installed
- See CRITICAL_FIXES_APPLIED.md for voice fixes
