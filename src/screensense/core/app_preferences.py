from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def normalize_app_key(process_name: str, window_title: str) -> str:
    process = (process_name or "unknown").strip().lower()
    title = (window_title or "unknown").strip().lower()
    return f"{process}|{title[:80]}"


@dataclass(slots=True)
class AppPreference:
    threshold_delta: float = 0.0
    samples: int = 0


class AppPreferenceStore:
    def __init__(self, *, enabled: bool, path: str) -> None:
        self._enabled = enabled
        self._path = Path(path)
        self._prefs: dict[str, AppPreference] = self._load()

    def threshold_for(self, *, base_threshold: float, app_key: str) -> float:
        if not self._enabled:
            return base_threshold
        pref = self._prefs.get(app_key)
        if pref is None:
            return base_threshold
        return self._clamp(base_threshold + pref.threshold_delta)

    def record_feedback(self, *, app_key: str, event: str, reason: str = "") -> None:
        if not self._enabled:
            return
        pref = self._prefs.get(app_key)
        if pref is None:
            pref = AppPreference()
            self._prefs[app_key] = pref
        if event == "action_denied":
            pref.threshold_delta = self._clamp_delta(pref.threshold_delta + 0.04)
        elif event == "action_executed":
            pref.threshold_delta = self._clamp_delta(pref.threshold_delta - 0.02)
        elif event == "action_skipped" and reason == "non_executable":
            pref.threshold_delta = self._clamp_delta(pref.threshold_delta + 0.01)
        pref.samples += 1
        self._save()

    def snapshot(self, app_key: str) -> dict[str, float | int]:
        pref = self._prefs.get(app_key, AppPreference())
        return {
            "threshold_delta": round(pref.threshold_delta, 4),
            "samples": pref.samples,
        }

    def _load(self) -> dict[str, AppPreference]:
        if not self._enabled or not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            data = payload.get("apps", {})
            out: dict[str, AppPreference] = {}
            for key, value in data.items():
                out[key] = AppPreference(
                    threshold_delta=float(value.get("threshold_delta", 0.0)),
                    samples=int(value.get("samples", 0)),
                )
            return out
        except Exception:
            return {}

    def _save(self) -> None:
        if not self._enabled:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "apps": {
                key: {
                    "threshold_delta": round(pref.threshold_delta, 4),
                    "samples": pref.samples,
                }
                for key, pref in self._prefs.items()
            }
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _clamp_delta(value: float) -> float:
        return max(-0.2, min(0.2, value))
