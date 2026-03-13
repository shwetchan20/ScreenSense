"""
ARIA SYSTEM DIAGNOSTICS
Run this from your screensense project root:
  python aria_diagnostics.py

Tests every component and shows exactly what's broken.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}✅ PASS{RESET}"
FAIL = f"{RED}❌ FAIL{RESET}"
WARN = f"{YELLOW}⚠️  WARN{RESET}"
INFO = f"{CYAN}ℹ️  INFO{RESET}"

results: list[dict[str, str]] = []


def log(status: str, component: str, message: str, detail: str = "") -> None:
    results.append(
        {"status": status, "component": component, "message": message, "detail": detail}
    )
    detail_str = f"\n         {DIM}{detail}{RESET}" if detail else ""
    print(f"  {status}  {BOLD}{component:<28}{RESET} {message}{detail_str}")


def section(title: str) -> None:
    print(f"\n{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{CYAN}{'─' * 60}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────
section("1. ENVIRONMENT & CONFIG")

env_path = Path(".env")
if env_path.exists():
    log(PASS, ".env file", "exists")
    from dotenv import dotenv_values

    env = dotenv_values(".env")

    critical_keys = [
        "GEMINI_API_KEY",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_BASE_URL",
        "REASONING_MODE",
        "CONFIDENCE_THRESHOLD",
        "IMPACT_SCORE_THRESHOLD",
        "LOCAL_LLM_ESCALATE_CONFIDENCE_THRESHOLD",
    ]
    for key in critical_keys:
        val = env.get(key, "")
        if val:
            display = val[:20] + "..." if len(val) > 20 else val
            log(PASS, key, f"set → {display}")
        else:
            log(FAIL, key, "NOT SET or empty")

    ct = float(env.get("CONFIDENCE_THRESHOLD", 0))
    elt = float(env.get("LOCAL_LLM_ESCALATE_CONFIDENCE_THRESHOLD", 0))
    ist = float(env.get("IMPACT_SCORE_THRESHOLD", 0))

    if ist < elt < ct:
        log(PASS, "Threshold alignment", f"impact({ist}) < escalate({elt}) < speak({ct})")
    else:
        log(
            FAIL,
            "Threshold alignment",
            f"WRONG ORDER: impact={ist} escalate={elt} speak={ct}",
            "Should be: IMPACT_SCORE_THRESHOLD < LOCAL_LLM_ESCALATE < CONFIDENCE_THRESHOLD",
        )

    tg_token = env.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = env.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        log(PASS, "Telegram config", "token + chat_id both set")
    elif tg_token:
        log(WARN, "Telegram config", "token set but TELEGRAM_CHAT_ID missing")
    else:
        log(WARN, "Telegram config", "not configured — Telegram features disabled")

    if env.get("DEMO_FORCE_SPEAK", "").lower() in ("1", "true"):
        log(WARN, "DEMO_FORCE_SPEAK", "ON — disable after demo recording")
    else:
        log(INFO, "DEMO_FORCE_SPEAK", "off (set to true before recording demo)")
else:
    log(FAIL, ".env file", "NOT FOUND — copy .env.example to .env")


# ─────────────────────────────────────────────────────────────────────────────
# 2. PYTHON PACKAGES
# ─────────────────────────────────────────────────────────────────────────────
section("2. PYTHON PACKAGES")

packages = {
    "google.generativeai": ("google-generativeai", True),
    "ollama": ("ollama", True),
    "playwright.async_api": ("playwright", True),
    "telegram": ("python-telegram-bot", True),
    "uiautomation": ("uiautomation", True),
    "sqlite3": ("built-in", True),
    "edge_tts": ("edge-tts", True),
    "mss": ("mss", True),
    "numpy": ("numpy", True),
    "pyautogui": ("pyautogui", False),
    "pyperclip": ("pyperclip", False),
    "faster_whisper": ("faster-whisper", False),
    "rapidocr_onnxruntime": ("rapidocr-onnxruntime", False),
}

for module, (pip_name, required) in packages.items():
    try:
        importlib.import_module(module)
        log(PASS, module, "installed")
    except ImportError:
        status = FAIL if required else WARN
        hint = f"pip install {pip_name}"
        if module == "playwright.async_api":
            hint += " && playwright install chromium"
        log(
            status,
            module,
            "NOT installed" if required else "optional — not installed",
            hint,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. OLLAMA / LOCAL LLM
# ─────────────────────────────────────────────────────────────────────────────
section("3. LOCAL LLM (OLLAMA + QWEN)")


async def check_ollama() -> None:
    try:
        import httpx
        from dotenv import dotenv_values

        env = dotenv_values(".env")
        url = env.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
        model = env.get("LOCAL_LLM_MODEL", "qwen2.5:latest")

        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{url}/api/tags")
            if r.status_code == 200:
                data = r.json()
                models = [m["name"] for m in data.get("models", [])]
                if model in models:
                    log(PASS, "Ollama", f"running, {model} found")
                else:
                    log(
                        WARN,
                        "Ollama",
                        f"running but {model} NOT found",
                        f"Available: {models[:3]} — run: ollama pull {model}",
                    )
            else:
                log(FAIL, "Ollama", f"HTTP {r.status_code}")
    except Exception:
        log(FAIL, "Ollama", "not reachable", "Start with: ollama serve")

    try:
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{url}/api/generate",
                json={"model": model, "prompt": "Say: ARIA online", "stream": False},
            )
            if r.status_code == 200:
                resp = r.json().get("response", "")
                log(PASS, "Qwen inference", f"responded: '{resp[:50]}'")
            else:
                log(FAIL, "Qwen inference", f"HTTP {r.status_code}")
    except Exception as e:
        log(FAIL, "Qwen inference", str(e)[:80])


asyncio.run(check_ollama())


# ─────────────────────────────────────────────────────────────────────────────
# 4. GEMINI API
# ─────────────────────────────────────────────────────────────────────────────
section("4. GEMINI API")


async def check_gemini() -> None:
    try:
        import google.generativeai as genai
        from dotenv import dotenv_values

        env = dotenv_values(".env")
        key = env.get("GEMINI_API_KEY", "")
        if not key:
            log(FAIL, "Gemini API", "GEMINI_API_KEY not set")
            return
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        r = model.generate_content("Reply with exactly: ARIA_OK")
        text = r.text.strip()
        if "ARIA_OK" in text:
            log(PASS, "Gemini API", "responding correctly")
        else:
            log(WARN, "Gemini API", f"responded but unexpected: '{text[:50]}'")
    except Exception as e:
        err = str(e)
        if "quota" in err.lower():
            log(WARN, "Gemini API", "QUOTA EXHAUSTED", err[:120])
        elif "api_key" in err.lower():
            log(FAIL, "Gemini API", "invalid API key", err[:80])
        else:
            log(FAIL, "Gemini API", str(e)[:80])


asyncio.run(check_gemini())


# ─────────────────────────────────────────────────────────────────────────────
# 5. BROWSER / PLAYWRIGHT
# ─────────────────────────────────────────────────────────────────────────────
section("5. BROWSER (PLAYWRIGHT)")


async def check_playwright() -> None:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(
                "https://html.duckduckgo.com/html/?q=python+asyncio",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            log(PASS, "Playwright launch", "chromium launched + navigated")

            content = await page.evaluate(
                """() => {
                    const items = [];
                    document.querySelectorAll('.result__title')
                        .forEach(el => items.push(el.innerText.trim()));
                    document.querySelectorAll('.result__snippet')
                        .forEach(el => items.push(el.innerText.trim()));
                    return items.slice(0, 6).join(' | ');
                }"""
            )

            if content and len(content) > 50:
                log(
                    PASS,
                    "DDG content extraction",
                    f"{len(content)} chars — '{content[:80]}...'",
                )
            else:
                fallback = await page.inner_text("body")
                fallback = fallback[:200].replace("\n", " ")
                log(
                    WARN,
                    "DDG content extraction",
                    "primary selectors returned empty",
                    "Fallback body text: "
                    f"'{fallback}'\n"
                    "         Fix: update CSS selectors in browser_ops.py",
                )

            await browser.close()
    except Exception as e:
        log(FAIL, "Playwright", str(e)[:100], "Run: playwright install chromium")


asyncio.run(check_playwright())


# ─────────────────────────────────────────────────────────────────────────────
# 6. TELEGRAM BOT
# ─────────────────────────────────────────────────────────────────────────────
section("6. TELEGRAM BOT")


async def check_telegram() -> None:
    try:
        from telegram import Bot
        from dotenv import dotenv_values

        env = dotenv_values(".env")
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        chat = env.get("TELEGRAM_CHAT_ID", "")

        if not token:
            log(WARN, "Telegram bot", "TELEGRAM_BOT_TOKEN not set — skipping")
            return

        bot = Bot(token=token)
        info = await bot.get_me()
        log(PASS, "Telegram bot", f"connected as @{info.username}")

        if chat:
            log(INFO, "Telegram chat_id", f"configured: {chat}")
        else:
            log(WARN, "Telegram chat_id", "TELEGRAM_CHAT_ID not set")
    except Exception as e:
        err = str(e)
        if "401" in err:
            log(FAIL, "Telegram bot", "invalid token (401 Unauthorized)")
        elif "network" in err.lower() or "connect" in err.lower():
            log(FAIL, "Telegram bot", "network error — check internet")
        else:
            log(FAIL, "Telegram bot", str(e)[:100])


asyncio.run(check_telegram())


# ─────────────────────────────────────────────────────────────────────────────
# 7. UI AUTOMATION
# ─────────────────────────────────────────────────────────────────────────────
section("7. UI AUTOMATION (WINDOWS)")

try:
    import uiautomation as auto

    window = auto.GetForegroundControl()
    title = window.Name if window else "unknown"
    log(PASS, "uiautomation", f"active window: '{title}'")

    children = window.GetChildren() if window else []
    log(PASS, "UI element tree", f"{len(children)} child elements found")
except Exception as e:
    log(FAIL, "uiautomation", str(e)[:100], "pip install uiautomation")


# ─────────────────────────────────────────────────────────────────────────────
# 8. SQLITE MEMORY
# ─────────────────────────────────────────────────────────────────────────────
section("8. SQLITE MEMORY DATABASE")

try:
    import sqlite3
    from dotenv import dotenv_values

    env = dotenv_values(".env")
    db_path = env.get("MEMORY_SQLITE_PATH", "runtime/aria_memory.db")

    if Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        log(PASS, "SQLite DB", f"exists — tables: {tables}")

        expected = ["interactions", "preferences", "session_goals", "telegram_history"]
        for t in expected:
            if t in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {t}")
                count = cursor.fetchone()[0]
                log(PASS, f"  table:{t}", f"{count} rows")
            else:
                log(FAIL, f"  table:{t}", "MISSING")

        conn.close()
    else:
        log(
            WARN,
            "SQLite DB",
            f"not found at {db_path}",
            "Will be created on first ARIA run",
        )
except Exception as e:
    log(FAIL, "SQLite DB", str(e)[:100])


# ─────────────────────────────────────────────────────────────────────────────
# 9. TTS / VOICE
# ─────────────────────────────────────────────────────────────────────────────
section("9. TTS / VOICE OUTPUT")


async def check_tts() -> None:
    try:
        import edge_tts

        communicate = edge_tts.Communicate("ARIA online.", voice="en-IN-NeerjaNeural")
        out = Path("runtime/diag_tts_test.mp3")
        out.parent.mkdir(exist_ok=True)
        await communicate.save(str(out))
        if out.exists() and out.stat().st_size > 1000:
            log(PASS, "edge-tts", f"generated {out.stat().st_size} bytes")
            out.unlink()
        else:
            log(FAIL, "edge-tts", "file too small or empty")
    except Exception as e:
        log(FAIL, "edge-tts", str(e)[:100])


asyncio.run(check_tts())


# ─────────────────────────────────────────────────────────────────────────────
# 10. SCREENSENSE SOURCE TREE
# ─────────────────────────────────────────────────────────────────────────────
section("10. SOURCE FILE STRUCTURE")

expected_files = [
    "src/screensense/app.py",
    "src/screensense/config.py",
    "src/screensense/core/coordinator.py",
    "src/screensense/core/interrupt_brain.py",
    "src/screensense/core/action_gate.py",
    "src/screensense/core/response_cleaner.py",
    "src/screensense/core/session_lifecycle.py",
    "src/screensense/core/health_monitor.py",
    "src/screensense/perception/ui_context.py",
    "src/screensense/perception/semantic_change.py",
    "src/screensense/inference/hybrid_inference.py",
    "src/screensense/inference/local_qwen.py",
    "src/screensense/integrations/telegram_bot.py",
    "src/screensense/integrations/voice.py",
    "src/screensense/memory/sqlite_store.py",
    "src/screensense/skills/browser_ops.py",
    "src/screensense/skills/code_ops.py",
    "src/screensense/skills/file_ops.py",
    "src/screensense/skills/system_ops.py",
    "src/screensense/ui/orb_overlay.py",
    "src/screensense/ui/dashboard.html",
]

for f in expected_files:
    p = Path(f)
    if p.exists():
        size = p.stat().st_size
        log(PASS, f.split("/")[-1], f"{size:,} bytes")
    else:
        log(FAIL, f.split("/")[-1], f"MISSING — {f}")


# ─────────────────────────────────────────────────────────────────────────────
# 11. BROWSER PIPELINE DEEP TEST
# ─────────────────────────────────────────────────────────────────────────────
section("11. BROWSER → QWEN PIPELINE (END-TO-END)")


async def check_browser_pipeline() -> None:
    print(f"\n  {DIM}Simulating: 'search python asyncio'{RESET}\n")

    content = ""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(
                "https://html.duckduckgo.com/html/?q=python+asyncio+tutorial",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            content = await page.evaluate(
                """() => {
                    const items = [];
                    document.querySelectorAll('.result__title')
                        .forEach(el => items.push('T: ' + el.innerText.trim()));
                    document.querySelectorAll('.result__snippet')
                        .forEach(el => items.push('S: ' + el.innerText.trim()));
                    document.querySelectorAll('.result__url')
                        .forEach(el => items.push('U: ' + el.innerText.trim()));
                    if (items.length === 0) {
                        return document.body.innerText
                            .replace(/\\s+/g,' ').slice(0,1000);
                    }
                    return items.slice(0,12).join('\\n');
                }"""
            )
            await browser.close()

        if content and len(content) > 100:
            log(
                PASS,
                "STEP 1: Browser search",
                f"{len(content)} chars extracted",
                f"Preview: {content[:120].replace(chr(10),' ')}",
            )
        else:
            log(
                FAIL,
                "STEP 1: Browser search",
                "empty result — selectors broken",
                "Fix CSS selectors in browser_ops.py",
            )
            return
    except Exception as e:
        log(FAIL, "STEP 1: Browser search", str(e)[:100])
        return

    try:
        import httpx
        from dotenv import dotenv_values

        env = dotenv_values(".env")
        url = env.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
        model = env.get("LOCAL_LLM_MODEL", "qwen2.5:latest")

        prompt = f"""You are ARIA, Shwet's co-pilot.
No bullet points. Max 3 sentences. No markdown.

Search results for 'python asyncio tutorial':
{content[:800]}

Based ONLY on above results, give Shwet
the top 2 URLs and one sentence summary.
Do not use training knowledge."""

        log(INFO, "STEP 2: Qwen prompt", f"{len(prompt)} chars — sending...")

        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                f"{url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            if r.status_code == 200:
                response = r.json().get("response", "")
                log(
                    PASS,
                    "STEP 2: Qwen response",
                    f"{len(response)} chars",
                    f"Response: {response[:200]}",
                )

                banned = [
                    "here's what",
                    "here is what",
                    "i would recommend",
                    "feel free",
                    "as an ai",
                    "i notice that",
                    "it appears that",
                    "certainly!",
                    "sure!",
                    "great!",
                ]
                found_banned = [p for p in banned if p in response.lower()]
                if found_banned:
                    log(
                        FAIL,
                        "STEP 3: Personality check",
                        f"2001 phrases found: {found_banned}",
                        "response_cleaner.py not running or prompt wrong",
                    )
                else:
                    log(PASS, "STEP 3: Personality check", "no banned phrases found")

                if any(
                    line.strip().startswith(("1.", "2.", "3.", "-", "*", "•"))
                    for line in response.split("\n")
                ):
                    log(
                        FAIL,
                        "STEP 4: Format check",
                        "bullet points / numbered list detected",
                        "ARIA must never use lists — fix system prompt",
                    )
                else:
                    log(PASS, "STEP 4: Format check", "no bullet points or lists")
            else:
                log(FAIL, "STEP 2: Qwen response", f"HTTP {r.status_code}")
    except Exception as e:
        log(FAIL, "STEP 2: Qwen call", str(e)[:100])


asyncio.run(check_browser_pipeline())


# ─────────────────────────────────────────────────────────────────────────────
# 12. RESPONSE CLEANER
# ─────────────────────────────────────────────────────────────────────────────
section("12. RESPONSE CLEANER")

try:
    sys.path.insert(0, "src")
    from screensense.core.response_cleaner import clean_response

    test_cases = [
        ("On the screen, I see VS Code open.", "should remove 'On the screen, I see'"),
        (
            "Certainly! I would recommend fixing line 42.",
            "should remove 'Certainly!' and 'I would recommend'",
        ),
        ("Great! Here's what you can do:", "should remove 'Great!' and 'Here's what you can do'"),
        ("It appears that your code has an error.", "should remove 'It appears that'"),
        ("ARIA is watching your screen!", "should remove exclamation mark"),
    ]

    all_pass = True
    for dirty, description in test_cases:
        cleaned = clean_response(dirty)
        changed = cleaned.strip() != dirty.strip()
        if changed:
            log(
                PASS,
                "response_cleaner",
                description,
                f"'{dirty[:40]}' → '{cleaned[:40]}'",
            )
        else:
            log(
                FAIL,
                "response_cleaner",
                f"DID NOT clean: {description}",
                f"Input:  '{dirty}'\nOutput: '{cleaned}'",
            )
            all_pass = False

    if all_pass:
        log(PASS, "response_cleaner overall", "all test cases passing")
except ImportError as e:
    log(FAIL, "response_cleaner", f"cannot import: {e}")
except Exception as e:
    log(FAIL, "response_cleaner", str(e)[:100])


# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{CYAN}{'═' * 60}{RESET}")
print(f"{BOLD}{CYAN}  DIAGNOSTIC SUMMARY{RESET}")
print(f"{CYAN}{'═' * 60}{RESET}\n")

passes = sum(1 for r in results if "PASS" in r["status"])
fails = sum(1 for r in results if "FAIL" in r["status"])
warnings = sum(1 for r in results if "WARN" in r["status"])
total = len(results)

print(f"  Total checks : {total}")
print(f"  {GREEN}Passing      : {passes}{RESET}")
print(f"  {RED}Failing      : {fails}{RESET}")
print(f"  {YELLOW}Warnings     : {warnings}{RESET}")

if fails == 0:
    print(f"\n  {GREEN}{BOLD}🔥 ARIA is healthy. All systems go.{RESET}")
else:
    print(f"\n  {RED}{BOLD}Critical issues to fix:{RESET}")
    for r in results:
        if "FAIL" in r["status"]:
            detail = f" → {r['detail']}" if r["detail"] else ""
            print(f"  {RED}→ {r['component']}: {r['message']}{detail}{RESET}")

report_path = Path("runtime/aria_diagnostic_report.json")
report_path.parent.mkdir(exist_ok=True)
with report_path.open("w", encoding="utf-8") as f:
    json.dump(
        {
            "timestamp": datetime.now().isoformat(),
            "summary": {"total": total, "pass": passes, "fail": fails, "warn": warnings},
            "results": [
                {
                    k: v.replace("\033[" + c, "")
                    for k, v in r.items()
                    for c in ["92m", "91m", "93m", "96m", "2m", "1m", "0m"]
                }
                for r in results
            ],
        },
        f,
        indent=2,
        default=str,
    )

print(f"\n  {DIM}Full report saved: {report_path}{RESET}\n")
