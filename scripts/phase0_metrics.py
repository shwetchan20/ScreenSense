from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from screensense.ui.data import read_recent_events


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


def main() -> int:
    audit_path = os.getenv("AUDIT_LOG_PATH", "runtime/audit.log.jsonl")
    limit = int(os.getenv("PHASE0_METRICS_LIMIT", "1200"))
    events = read_recent_events(audit_path, limit=limit)

    if not events:
        print(f"[phase0] no events found at {Path(audit_path).as_posix()}")
        print("[phase0] start the agent and wait ~30s, then re-run.")
        return 2

    counts = Counter(str(e.get("event") or "unknown") for e in events)

    def count_prefix(prefix: str) -> int:
        return sum(v for k, v in counts.items() if k.startswith(prefix))

    submitted = counts.get("vision_submitted_async", 0)
    interrupts_allowed = sum(
        1
        for e in events
        if e.get("event") == "interrupt_evaluated" and e.get("allow_interrupt") is True
    )
    actions_executed = counts.get("action_executed", 0)
    errors = counts.get("vision_error", 0) + counts.get("tick_error", 0)

    # Change score distribution (from coordinator print/audit events).
    scores: list[float] = []
    for e in events:
        if e.get("event") in {"vision_submitted_async", "semantic_change_skipped"}:
            scores.append(_as_float(e.get("change_score")))

    avg_score = (sum(scores) / len(scores)) if scores else 0.0
    p95_score = 0.0
    if scores:
        sorted_scores = sorted(scores)
        idx = int(0.95 * (len(sorted_scores) - 1))
        p95_score = sorted_scores[max(0, idx)]

    print("=== Phase 0 metrics (from audit log) ===")
    print(f"audit_path: {audit_path}")
    print(f"events_scanned: {len(events)}")
    print("")
    print("--- change detection ---")
    print(f"avg_change_score: {avg_score:.3f}")
    print(f"p95_change_score: {p95_score:.3f}")
    print(f"semantic_change_skipped: {counts.get('semantic_change_skipped', 0)}")
    print("")
    print("--- inference load ---")
    print(f"vision_submitted_async: {submitted}")
    print(f"vision_skipped_*: {count_prefix('vision_skipped_')}")
    print(f"  - focus_mode: {counts.get('vision_skipped_focus_mode', 0)}")
    print(f"  - fast_path: {counts.get('vision_skipped_fast_path', 0)}")
    print(f"  - inflight: {counts.get('vision_skipped_inflight', 0)}")
    print(f"  - backoff: {counts.get('vision_skipped_backoff_window', 0)}")
    print(f"  - circuit_breaker: {counts.get('vision_skipped_circuit_breaker', 0)}")
    print(f"  - rate_guard: {counts.get('vision_skipped_rate_guard', 0)}")
    print("")
    print("--- interrupts & actions ---")
    print(f"interrupts_allowed: {interrupts_allowed}")
    print(f"action_executed: {actions_executed}")
    print(f"action_denied: {counts.get('action_denied', 0)}")
    print(f"action_skipped: {counts.get('action_skipped', 0)}")
    print("")
    print("--- stability ---")
    print(f"errors (vision_error+tick_error): {errors}")
    print(f"vision_circuit_opened: {counts.get('vision_circuit_opened', 0)}")
    print("")
    top = counts.most_common(12)
    print("--- top events ---")
    for name, c in top:
        print(f"{name}: {c}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

