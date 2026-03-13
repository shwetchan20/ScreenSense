from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def read_recent_events(path: str, limit: int = 200) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    lines = file_path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def derive_ui_state(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("event") == "interrupt_evaluated" and event.get("allow_interrupt") is True:
            return "notify"
    return "ghost"


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(event.get("event", "unknown") for event in events)
    reasons = Counter(str(event.get("reason", "")) for event in events if "reason" in event)
    latest_message = ""
    latest_context = ""
    for event in reversed(events):
        if event.get("event") == "interrupt_evaluated" and event.get("message"):
            latest_message = str(event.get("message", ""))
            latest_context = str(event.get("context", ""))
            break
    return {
        "total_events": len(events),
        "event_counts": counts,
        "reason_counts": reasons,
        "latest_message": latest_message,
        "latest_context": latest_context,
        "ui_state": derive_ui_state(events),
    }

