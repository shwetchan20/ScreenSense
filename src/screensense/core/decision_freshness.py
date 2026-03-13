from __future__ import annotations

import time


def is_stale_decision(
    *,
    submitted_ts: float,
    max_age_seconds: float,
    submitted_app_key: str,
    current_app_key: str,
    require_same_app: bool,
) -> tuple[bool, str]:
    age = max(0.0, time.time() - submitted_ts)
    if age > max_age_seconds:
        return True, "stale_age"
    if require_same_app and submitted_app_key and current_app_key and submitted_app_key != current_app_key:
        return True, "stale_app_switched"
    return False, "fresh"
