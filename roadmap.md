# ARIA — Phased Build Roadmap
## Steal Everything. Build Incrementally. Ship Fast.

---

## THE NORTH STAR

```
ARIA = Your laptop, talking.
       Knows everything on screen.
       Acts on your behalf.
       Never sleeps.
       Gets smarter every week.
```

---

## CURRENT STATE (What You Have)

```
✅ Screen loop (2s interval)
✅ Telegram two-way 
✅ DDG web search (real results)
✅ open_url via httpx
✅ UI Automation (window title, file, project)
✅ SQLite memory (20 telegram messages)
✅ edge-tts voice
✅ Qwen local inference
✅ Gemini vision (key needed)
✅ Response cleaner
✅ File ops, Code ops, System ops
✅ Morning brief skeleton
✅ Interrupt brain
✅ Action gate

❌ Screen content still shallow (no editor text)
❌ change_score always 0.00 (no proactive alerts)
❌ Gmail / Calendar / GitHub
❌ Long-term learning memory
❌ Laptop wake/sleep awareness  
❌ Watchdog auto-restart
❌ Real code fixing end-to-end
```

---

---

# PHASE 0 — STABILISE (This Week)
## Fix what's broken before adding anything new

**Time:** 3-4 days  
**Goal:** Every existing feature works reliably

---

### 0.1 — Fix change_score (Steal from: Screenpipe)

**Why it's 0.00:**  
Semantic change detection compares UI context snapshots.  
But UI context is shallow — only window title changes.  
Same title = score 0. Always.

**What Screenpipe does:**  
`github.com/mediar-ai/screenpipe`  
They diff OCR text content between frames, not just titles.  
They weight by: new text appeared, error keywords, element focus changed.

**What to tell Cursor:**
```
"In perception/semantic_change.py,
 the change detector only compares window titles.
 
 Add content-based scoring:
 
 def compute_change_score(prev: dict, curr: dict) -> tuple[float, list[str]]:
     score = 0.0
     reasons = []
     
     # Title changed
     if prev.get('window_title') != curr.get('window_title'):
         score += 0.3
         reasons.append('window_title_changed')
     
     # App changed
     if prev.get('active_app') != curr.get('active_app'):
         score += 0.25
         reasons.append('active_app_changed')
     
     # File changed in VS Code
     if prev.get('current_file') != curr.get('current_file'):
         score += 0.4
         reasons.append('file_changed')
     
     # Error appeared in terminal
     curr_terminal = curr.get('terminal_output', '')
     prev_terminal = prev.get('terminal_output', '')
     error_keywords = ['error','traceback','exception',
                       'failed','denied','not found']
     if curr_terminal != prev_terminal:
         if any(k in curr_terminal.lower() for k in error_keywords):
             score = min(1.0, score + 0.6)
             reasons.append('error_detected')
         else:
             score += 0.2
             reasons.append('terminal_changed')
     
     # New errors in error_list
     if curr.get('error_list') and not prev.get('error_list'):
         score = min(1.0, score + 0.7)
         reasons.append('new_errors')
     
     # Editor content changed significantly
     curr_code = curr.get('editor_content', '')
     prev_code = prev.get('editor_content', '')
     if curr_code and prev_code:
         diff_ratio = len(set(curr_code) - set(prev_code)) / max(len(curr_code), 1)
         if diff_ratio > 0.1:
             score += 0.15
             reasons.append('code_changed')
     
     return min(1.0, score), reasons"
```

---

### 0.2 — Fix VS Code editor content reading

**Why it's empty:**  
`uiautomation.GetFocusedControl().Value` returns empty for VS Code  
because VS Code uses a custom renderer (Monaco), not standard Win32 controls.

**Real fix — clipboard trick (steal from: Open Interpreter):**
```
"In perception/ui_context.py _enrich_ide():

VS Code Monaco editor doesn't expose text
via standard UI Automation Value property.

Use clipboard approach instead:
import pyperclip
import pyautogui
import time

def _read_vscode_content() -> str:
    try:
        # Save current clipboard
        old = pyperclip.paste()
        
        # Select all + copy in active editor
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.1)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.2)
        
        content = pyperclip.paste()
        
        # Restore clipboard
        pyperclip.copy(old)
        
        # Move cursor back to original position  
        pyautogui.hotkey('ctrl', 'z')
        
        return content[:1000] if content else ''
    except Exception:
        return ''

Call this in _enrich_ide() when visible_code is empty.
Only run every 10 seconds max (expensive)."
```

---

### 0.3 — Add ARIA_API_KEY to .env and restart clean

```
GEMINI_API_KEY=get_from_aistudio.google.com
IMPACT_SCORE_THRESHOLD=0.55
LOCAL_LLM_ESCALATE_CONFIDENCE_THRESHOLD=0.72
CONFIDENCE_THRESHOLD=0.80
```

---

### 0.4 — Watchdog (Steal from: PM2 / Supervisor patterns)

**What it does:** If ARIA crashes, auto-restart within 3 seconds.

Create `aria_watchdog.py` in project root:
```python
import subprocess
import time
import sys

def run():
    while True:
        print("[Watchdog] Starting ARIA...")
        proc = subprocess.Popen(
            [sys.executable, "-m", "screensense.app"],
            cwd="."
        )
        proc.wait()
        code = proc.returncode
        print(f"[Watchdog] ARIA exited with code {code}")
        if code == 0:
            print("[Watchdog] Clean exit. Not restarting.")
            break
        print("[Watchdog] Restarting in 3 seconds...")
        time.sleep(3)

if __name__ == "__main__":
    run()
```

Run ARIA as: `python aria_watchdog.py`

---

### 0.5 — Windows startup on boot

Create `aria_startup.bat` in project root:
```batch
@echo off
cd /d "C:\Users\shwet k\OneDrive\Desktop\screensense"
call .venv\Scripts\activate
python aria_watchdog.py
```

Add to Windows startup:
```
Win+R → shell:startup
Copy aria_startup.bat shortcut there
Done. ARIA starts on every boot.
```

---

**Phase 0 Deliverable:**
```
ARIA runs 24/7, auto-restarts on crash,
starts on boot, detects real screen changes,
proactive alerts fire when errors appear.
```

---

---

# PHASE 1 — INTELLIGENCE UPGRADE
## Better memory, better reasoning, better context
**Time:** 1 week  
**Source repos:** mem0, Screenpipe, SWE-agent

---

### 1.1 — Long-term Memory (Steal from: mem0)

**Repo:** `github.com/mem0ai/mem0`  
**What it does:** Semantic memory that learns over time.  
"Last time you had this error you fixed it by..."

**Install:**
```
pip install mem0ai
```

**Integration — replace sqlite_store.py memory reads:**
```python
# In memory/sqlite_store.py add alongside existing:

from mem0 import Memory

class ARIAMemory:
    def __init__(self):
        self.m = Memory()
        self.user_id = "shwet"
    
    def remember(self, text: str, category: str = "general"):
        self.m.add(text, user_id=self.user_id, 
                   metadata={"category": category})
    
    def recall(self, query: str, limit: int = 5) -> list[str]:
        results = self.m.search(query, user_id=self.user_id, limit=limit)
        return [r['memory'] for r in results]
    
    def recall_errors(self, error_text: str) -> str:
        memories = self.recall(f"error: {error_text}")
        if memories:
            return f"Previously: {memories[0]}"
        return ""

# Usage in coordinator.py:
# When error detected:
#   memory.remember(f"fixed {error} by {solution}", "code_fix")
# When building Qwen prompt:
#   past = memory.recall(current_error)
#   inject into prompt
```

---

### 1.2 — Screen History Index (Steal from: Screenpipe)

**What Screenpipe does:**  
Stores every screen state with timestamp.  
You can ask "what was I doing at 3pm yesterday."

**Lightweight version for ARIA:**
```python
# Add to memory/sqlite_store.py:

# New table: screen_history
CREATE TABLE screen_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    app TEXT,
    file TEXT,
    content_hash TEXT,
    summary TEXT
);

# In coordinator.py, every 30 seconds:
# snapshot current ui_context
# generate 1-line summary via Qwen
# store in screen_history

# Telegram command "what was I doing at 3pm":
# Query screen_history by timestamp
# Return summary
```

---

### 1.3 — Code Intelligence (Steal from: SWE-agent)

**Repo:** `github.com/princeton-nlp/SWE-agent`  
**What they do:** Navigate codebases, find bugs, write fixes, verify.

**Their key insight:** Don't read whole files. Use grep + targeted reads.

**What to steal for code_ops.py:**
```python
# Add these methods to CodeOps:

def find_in_codebase(self, pattern: str) -> str:
    """grep -r pattern across project"""
    import subprocess
    result = subprocess.run(
        ['grep', '-r', '-n', '--include=*.py', pattern, '.'],
        capture_output=True, text=True, timeout=10
    )
    return result.stdout[:2000]

def get_error_context(self, error_text: str) -> str:
    """Given an error, find the relevant code"""
    # Extract filename and line from traceback
    import re
    match = re.search(r'File "([^"]+)", line (\d+)', error_text)
    if not match:
        return ""
    filepath, lineno = match.group(1), int(match.group(2))
    
    # Read ±10 lines around error
    try:
        with open(filepath) as f:
            lines = f.readlines()
        start = max(0, lineno - 10)
        end = min(len(lines), lineno + 10)
        snippet = ''.join(lines[start:end])
        return f"Error at line {lineno}:\n{snippet}"
    except Exception:
        return ""

def propose_fix(self, error_text: str, code_context: str) -> str:
    """Ask Qwen to propose a fix given error + context"""
    # Build prompt with error + code context
    # Call local_qwen directly
    # Return proposed patch
    pass
```

---

### 1.4 — Proactive Research (New capability)

**What it does:**  
ARIA monitors topics you care about.  
You tell it "watch for updates on Gemini API".  
Every hour it checks. Tells you if something changed.

```python
# New file: skills/research_monitor.py

class ResearchMonitor:
    def __init__(self, browser_ops, memory, telegram_bot):
        self._browser = browser_ops
        self._memory = memory  
        self._tg = telegram_bot
        self._watches: list[dict] = []
        self._last_check = 0.0
    
    def add_watch(self, topic: str, interval_minutes: int = 60):
        self._watches.append({
            'topic': topic,
            'interval': interval_minutes * 60,
            'last_checked': 0.0,
            'last_result_hash': ''
        })
    
    async def tick(self):
        """Call from main loop every minute"""
        now = time.time()
        for watch in self._watches:
            if now - watch['last_checked'] < watch['interval']:
                continue
            results = self._browser.search_web_api(
                f"{watch['topic']} latest news"
            )
            result_hash = str(hash(results[:200]))
            if result_hash != watch['last_result_hash']:
                # Something changed
                self._tg.send_message(
                    f"update on {watch['topic']}: {results[:300]}"
                )
                watch['last_result_hash'] = result_hash
            watch['last_checked'] = now

# Telegram command: "watch gemini api updates"
# → adds to research monitor
```

---

**Phase 1 Deliverable:**
```
ARIA remembers past fixes.
ARIA indexes screen history.
ARIA finds bugs in your code intelligently.
ARIA proactively monitors topics you care about.
"Last time you had this error you fixed it by
 changing payload['user_id'] on line 42."
```

---

---

# PHASE 2 — AUTOMATION ARMS
## Gmail, Calendar, GitHub, Browser control
**Time:** 1-2 weeks  
**Source:** Composio, Skyvern, AgentKit

---

### 2.1 — Gmail + Calendar (Steal from: Composio)

**Repo:** `github.com/ComposioHQ/composio`  
**Why:** 200 pre-built integrations. Gmail in 10 lines.

**Install:**
```
pip install composio-core composio-openai
composio login
composio add gmail
composio add googlecalendar
```

**New skill: skills/gmail_ops.py**
```python
from composio_openai import ComposioToolSet, Action

class GmailOps:
    def __init__(self):
        self.toolset = ComposioToolSet()
    
    def get_unread(self, limit: int = 5) -> list[dict]:
        result = self.toolset.execute_action(
            action=Action.GMAIL_FETCH_EMAILS,
            params={"max_results": limit, "label": "UNREAD"}
        )
        return result.get('messages', [])
    
    def summarise_unread(self) -> str:
        emails = self.get_unread()
        if not emails:
            return "no unread emails"
        lines = []
        for e in emails[:5]:
            sender = e.get('from', 'unknown')
            subject = e.get('subject', 'no subject')
            lines.append(f"{sender}: {subject}")
        return "\n".join(lines)
    
    def send_email(self, to: str, subject: str, 
                   body: str) -> bool:
        result = self.toolset.execute_action(
            action=Action.GMAIL_SEND_EMAIL,
            params={"to": to, "subject": subject, "body": body}
        )
        return result.get('success', False)
    
    def draft_reply(self, email_id: str, 
                    body: str) -> bool:
        result = self.toolset.execute_action(
            action=Action.GMAIL_CREATE_EMAIL_DRAFT,
            params={"email_id": email_id, "body": body}
        )
        return result.get('success', False)


class CalendarOps:
    def __init__(self):
        self.toolset = ComposioToolSet()
    
    def get_today(self) -> list[dict]:
        result = self.toolset.execute_action(
            action=Action.GOOGLECALENDAR_LIST_EVENTS,
            params={"timeMin": "today", "maxResults": 10}
        )
        return result.get('events', [])
    
    def get_next_event(self) -> str:
        events = self.get_today()
        if not events:
            return "nothing scheduled today"
        next_e = events[0]
        title = next_e.get('summary', 'untitled')
        start = next_e.get('start', {}).get('dateTime', '')
        return f"{title} at {start[:16]}"
```

**Telegram commands this enables:**
```
"check my emails"    → summarise_unread()
"any emails from X"  → filter by sender
"what's on calendar" → get_today()
"remind me at 9pm"   → create_event()
"draft reply to X"   → draft_reply()
```

---

### 2.2 — GitHub Integration (Steal from: Composio)

```python
# Add to skills/github_ops.py

class GitHubOps:
    def __init__(self):
        self.toolset = ComposioToolSet()
    
    def get_open_issues(self, repo: str) -> str:
        result = self.toolset.execute_action(
            action=Action.GITHUB_LIST_ISSUES,
            params={"repo": repo, "state": "open"}
        )
        issues = result.get('issues', [])
        return "\n".join([
            f"#{i['number']}: {i['title']}" 
            for i in issues[:5]
        ])
    
    def create_pr(self, title: str, body: str, 
                  branch: str) -> str:
        result = self.toolset.execute_action(
            action=Action.GITHUB_CREATE_PULL_REQUEST,
            params={"title": title, "body": body, 
                    "head": branch}
        )
        return result.get('url', 'failed')
    
    def review_pr(self, pr_url: str) -> str:
        # Fetch PR diff via GitHub API
        # Send diff to Qwen for review
        # Return review comments
        pass
```

---

### 2.3 — Real Browser Control (Steal from: Skyvern + AgentKit)

**Repo:** `github.com/Skyvern-AI/skyvern`  
**What it does:** Vision + LLM to control ANY website.  
No CSS selectors. No brittle scripts. Just "fill this form."

**For ARIA — replace open_url_async with Skyvern for complex sites:**
```python
# In browser_ops.py add:

async def automate_browser(self, 
    url: str, 
    task: str
) -> str:
    """
    Use Skyvern for complex browser tasks:
    - Login to sites
    - Fill forms
    - Extract structured data
    - Handle CAPTCHAs
    
    task examples:
    "extract all product prices"
    "fill the contact form with my details"
    "click the subscribe button"
    """
    # Skyvern API call
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://localhost:8000/api/v1/tasks",
            json={"url": url, "navigation_goal": task}
        )
        task_id = r.json()['task_id']
        
        # Poll for completion
        for _ in range(30):
            await asyncio.sleep(2)
            status = await client.get(
                f"http://localhost:8000/api/v1/tasks/{task_id}"
            )
            data = status.json()
            if data['status'] == 'completed':
                return data.get('extracted_information', '')
    return ""
```

**Telegram commands this enables:**
```
"book a cab on ola"          → fills form
"order my usual from swiggy" → automates order
"extract prices from flipkart for iphone" → structured data
"log into my college portal" → handles login
```

---

### 2.4 — WhatsApp / Notification Hub

**Using: whatsapp-web.js (Node) or Baileys**
```
For Telegram → already working ✅
For WhatsApp → run a Node sidecar

# whatsapp_bridge.js
const { Client } = require('whatsapp-web.js');
const express = require('express');

const app = express();
const client = new Client();

app.post('/send', (req, res) => {
    const { to, message } = req.body;
    client.sendMessage(to, message);
    res.json({ ok: true });
});

app.listen(9999);

# In ARIA: 
# requests.post('http://localhost:9999/send', 
#               json={'to': '91XXXXXXXXXX@c.us', 
#                     'message': text})
```

**Or skip WhatsApp — Telegram already gives you everything.**  
WhatsApp adds complexity, Telegram has better bots.

---

**Phase 2 Deliverable:**
```
"check emails" → real Gmail summary
"what's today" → real Calendar events  
"remind me at 9" → creates Calendar event
"review my PR" → actual GitHub PR review
"book on ola" → browser fills form
ARIA proactively: "email from OrbitIQ, 
                   want me to draft a reply?"
```

---

---

# PHASE 3 — DEEP CODE CO-PILOT
## Sees errors, finds fixes, applies with approval
**Time:** 1 week  
**Source:** SWE-agent, Aider, Open Interpreter

---

### 3.1 — Error → Fix Pipeline (Steal from: SWE-agent + Aider)

**Repo:** `github.com/paul-gauthier/aider`  
**What Aider does:** Edits your code files via LLM.  
Understands the full codebase, not just one file.

**What to steal:**
```python
# Enhanced code_ops.py

class ErrorFixPipeline:
    """Full pipeline: detect → analyse → propose → apply"""
    
    def __init__(self, qwen_client, memory, action_gate):
        self._qwen = qwen_client
        self._memory = memory
        self._gate = action_gate
    
    async def handle_error(self, error_text: str, 
                           terminal_output: str) -> str:
        # Step 1: Check memory for past fixes
        past_fix = self._memory.recall_errors(error_text)
        if past_fix:
            return f"seen this before — {past_fix}"
        
        # Step 2: Extract file + line from traceback
        context = self._get_error_context(error_text)
        
        # Step 3: Search Stack Overflow
        so_results = browser_ops.search_stackoverflow(error_text)
        
        # Step 4: Ask Qwen for fix
        prompt = f"""
Error: {error_text}

Code context:
{context}

Stack Overflow solutions:
{so_results[:500]}

Propose the minimal fix. 
Output ONLY:
FILE: path/to/file.py
LINE: 42  
OLD: broken_code_here
NEW: fixed_code_here
EXPLANATION: one sentence
"""
        fix = self._qwen.generate(prompt)
        
        # Step 5: Parse and validate fix
        parsed = self._parse_fix(fix)
        if not parsed:
            return f"found the error, couldn't parse fix: {fix[:200]}"
        
        # Step 6: Request approval via Telegram
        preview = (f"fix: {parsed['file']} line {parsed['line']}\n"
                   f"- {parsed['old']}\n"
                   f"+ {parsed['new']}\n"
                   f"reason: {parsed['explanation']}")
        
        approved = self._gate.approve(preview, risk="medium")
        
        if approved:
            # Apply the fix
            self._apply_fix(parsed)
            # Remember it
            self._memory.remember(
                f"fixed '{error_text[:50]}' by: {parsed['explanation']}",
                "code_fix"
            )
            return "fixed and applied."
        
        return "fix ready, skipped on your call."
```

---

### 3.2 — Git Workflow Automation

```python
# In code_ops.py add:

def smart_commit(self) -> str:
    """
    1. Get git diff
    2. Ask Qwen to write commit message
    3. Commit with that message
    """
    diff = self.git_diff()
    if not diff:
        return "nothing to commit"
    
    prompt = f"""
Git diff:
{diff[:1000]}

Write a concise git commit message (max 72 chars).
Format: type(scope): description
Examples:
  fix(auth): correct JWT decode for PyJWT 2.0
  feat(telegram): add URL extraction for plain domains
  refactor(ui): simplify orb overlay state machine

Output ONLY the commit message, nothing else.
"""
    message = self._qwen.generate(prompt).strip()
    
    approved = self._gate.approve(
        f"commit: {message}", risk="low"
    )
    if approved:
        return self.git_commit(message)
    return f"proposed: '{message}' — skipped"

def auto_pr_description(self) -> str:
    """Generate PR description from commits since main"""
    log = self.run_command(['git', 'log', 
                            'main..HEAD', '--oneline'])
    diff = self.run_command(['git', 'diff', 'main'])
    # Ask Qwen to write PR description
    # Return markdown PR body
    pass
```

---

### 3.3 — Test Runner + Auto-fix

```python
# In code_ops.py:

async def run_tests_and_fix(self, 
    test_path: str = "tests/"
) -> str:
    """Run tests. For each failure, attempt fix."""
    
    result = self.run_command(['python', '-m', 'pytest', 
                               test_path, '-v', '--tb=short'])
    
    if 'failed' not in result.lower():
        return f"all tests passing"
    
    # Parse failures
    failures = self._parse_test_failures(result)
    
    summaries = []
    for failure in failures[:3]:  # max 3 auto-fixes
        fix_result = await self._error_pipeline.handle_error(
            failure['error'], failure['output']
        )
        summaries.append(f"{failure['test']}: {fix_result}")
    
    return "\n".join(summaries)
```

---

**Phase 3 Deliverable:**
```
Error appears in terminal
→ ARIA sees it in 3 seconds
→ searches Stack Overflow
→ finds the fix
→ sends diff to Telegram
→ you tap ✓
→ file patched automatically
→ git commit message written
→ "fixed. pushed. tests passing."
```

---

---

# PHASE 4 — PROACTIVE INTELLIGENCE
## ARIA acts without being asked
**Time:** 1-2 weeks  
**Source:** Custom + patterns from all above

---

### 4.1 — Morning Brief (Enhanced)

```
Every morning when laptop opens:

"Good morning Shwet. 8:14am.
 3 unread emails — one from OrbitIQ about the interview.
 Your OrbitIQ call is today at 2pm.
 4 open issues on screensense GitHub.
 ARIA uptime: 6h 23min.
 Today's goal from yesterday: finish telegram pipeline.
 Pick up where you left off?"
```

**What this needs:**  
Gmail → unread count + sender names  
Calendar → today's events  
GitHub → open issues  
Memory → yesterday's goal  

All from Phase 2 skills.

---

### 4.2 — Away Mode

```
When laptop is idle for 5+ minutes:
→ Switch to low-power monitoring
→ Watch for critical alerts only
→ If something important happens:
   Telegram notification to phone

"your training script just crashed.
 last output: CUDA out of memory.
 fix it remotely?"
```

```python
# In coordinator.py:

class AwayDetector:
    def __init__(self):
        self._last_input_ts = time.time()
        self._is_away = False
        self._away_threshold = 300  # 5 minutes
    
    def update(self):
        # Check last mouse/keyboard activity
        import ctypes
        info = ctypes.Structure()
        # GetLastInputInfo Windows API
        away = (time.time() - self._last_input_ts 
                > self._away_threshold)
        if away != self._is_away:
            self._is_away = away
            return "went_away" if away else "returned"
        return None
```

---

### 4.3 — Deadline Awareness

```
You told ARIA: "OrbitIQ interview is March 15"

Every session:
"3 days until OrbitIQ call.
 ARIA demo not tested end-to-end yet.
 5 features still marked TODO.
 Suggest: record demo today."

Every day it gets more urgent.
Day of: "interview in 4 hours. 
          demo ready? want to do a dry run?"
```

---

### 4.4 — Pattern Learning (Steal from: mem0 + custom)

```
After 2 weeks of use, ARIA knows:
→ You code best between 10pm-2am
→ You always forget to commit before sleeping
→ You get stuck on auth bugs specifically
→ You like concise answers, not explanations

ARIA adapts:
→ Nudges you to commit at midnight
→ Doesn't explain, just fixes
→ More aggressive on auth-related alerts
→ Quieter during your low-focus hours
```

---

**Phase 4 Deliverable:**
```
ARIA is genuinely proactive.
Acts without being asked.
Knows your patterns.
Feels like it understands you.
Not "how can I help" — 
"you've been on this bug for 90 minutes,
 found the fix, applying now."
```

---

---

# PHASE 5 — PACKAGE & SHIP
## ARIA as a product
**Time:** 2 weeks

---

### 5.1 — ARIA.exe (Steal from: PyInstaller patterns)

```
pip install pyinstaller
pyinstaller --onefile --windowed \
    --add-data "src;src" \
    --icon aria.ico \
    aria_watchdog.py

→ ARIA.exe
Double click. Running. No Python needed.
```

---

### 5.2 — Settings UI

```
Simple web UI at localhost:7070
Open from system tray icon

Settings:
→ Your name
→ Current project
→ Deadline date
→ Enable/disable features
→ Telegram setup wizard
→ Connected accounts (Gmail, Calendar, GitHub)
→ Notification preferences
→ View screen history
→ Memory browser
```

---

### 5.3 — Multi-user (Future)

```
ARIA as a SaaS:
→ Download ARIA.exe  
→ Login with Google
→ Your memories + settings sync to cloud
→ Access ARIA from any device via Telegram
→ Same ARIA, everywhere
```

---

---

# STEAL SHEET — Quick Reference

| What to steal | From where | What it gives ARIA |
|---|---|---|
| Screen indexing | Screenpipe | Screen history, time queries |
| Semantic memory | mem0 | "Last time you had this error..." |
| Gmail/Calendar | Composio | Email + calendar automation |
| GitHub ops | Composio | PR review, issue tracking |
| Browser automation | Skyvern | Login walls, form filling |
| Codebase navigation | SWE-agent | Intelligent file reading |
| Code editing | Aider | Apply fixes to real files |
| Code execution | Open Interpreter | Run anything safely |
| Change detection | Screenpipe | Real change_score |
| Watchdog | PM2 patterns | Auto-restart |

---

# INSTALL COMMANDS BY PHASE

```bash
# Phase 0 (now)
pip install httpx  # already done

# Phase 1
pip install mem0ai

# Phase 2  
pip install composio-core composio-openai
composio login
composio add gmail googlecalendar github

# Phase 3
pip install aider-chat  # optional - steal patterns only

# Phase 4
# All custom code, no new deps

# Phase 5
pip install pyinstaller
```

---

# THE ONE RULE

```
Build one phase at a time.
Test it. Make it reliable.
Then move to next phase.

A working Phase 1 beats 
a half-built Phase 4.

ARIA gets better every week.
That's the goal.
```
