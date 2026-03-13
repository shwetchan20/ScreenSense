# Demo Mode Quick Start

## 1. Enable Demo Mode

Edit `.env`:
```bash
DEMO_MODE=true
```

## 2. Start ARIA

```bash
python -m screensense.app
```

## 3. Trigger Responses

Open any window with these keywords in the title:

| Window Title Contains | ARIA Says |
|----------------------|-----------|
| "visual studio code" | "VS Code is open. I'm monitoring for errors..." |
| "stack overflow" | "I see you're on Stack Overflow..." |
| "github" | "You're browsing GitHub..." |
| "powershell" | "PowerShell terminal active..." |
| "python" | "Python code detected..." |
| "error" | "I notice an error on screen..." |
| "youtube" | "Watching a tutorial on YouTube?..." |
| "notion" | "Notion is open. Taking notes?..." |

## 4. Test Clipboard Triggers

Copy these exact words to clipboard:
- "help" → Explains what ARIA does
- "aria" → "Yes? I'm here..."
- "error" → "I'm checking for errors..."

## 5. Add Custom Trigger

Edit `src/screensense/demo_responses.py`:
```python
DEMO_RESPONSES: dict[str, str] = {
    "my keyword": "My custom response",
    # ... existing triggers
}
```

## 6. Disable Demo Mode

Edit `.env`:
```bash
DEMO_MODE=false
```

## That's It!

- Instant responses (no LLM wait)
- Perfect for demos
- 60+ built-in triggers
- See DEMO_MODE.md for full docs
