from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from screensense.config import load_settings
from screensense.ui.data import read_recent_events, summarize

app = FastAPI(title="ScreenSense UI", version="0.1.0")

_ROOT = Path(__file__).resolve().parent
_HTML = (_ROOT / "dashboard.html").read_text(encoding="utf-8")
_settings = load_settings()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _HTML


@app.get("/api/status")
def status(limit: int = Query(default=200, ge=10, le=1000)) -> dict[str, Any]:
    events = read_recent_events(_settings.audit_log_path, limit=limit)
    summary = summarize(events)
    return {
        "ui_state": summary["ui_state"],
        "latest_message": summary["latest_message"],
        "latest_context": summary["latest_context"],
        "total_events": summary["total_events"],
        "event_counts": summary["event_counts"],
        "reason_counts": summary["reason_counts"],
        "config": {
            "product_mode": _settings.product_mode,
            "confidence_threshold": _settings.confidence_threshold,
            "diff_threshold_percent": _settings.diff_threshold_percent,
            "agent_runtime_mode": _settings.agent_runtime_mode,
            "voice_preset": _settings.voice_preset,
            "voice_style": _settings.voice_style,
        },
    }


@app.get("/api/events")
def events(limit: int = Query(default=120, ge=10, le=1000)) -> dict[str, Any]:
    records = read_recent_events(_settings.audit_log_path, limit=limit)
    return {"events": records}
