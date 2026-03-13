from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass


@dataclass
class CheckItem:
    name: str
    required: bool
    reason: str
    ok: bool
    hint: str


def _check_import(module: str, *, required: bool, reason: str, hint: str) -> CheckItem:
    ok = importlib.util.find_spec(module) is not None
    return CheckItem(name=module, required=required, reason=reason, ok=ok, hint=hint)


def main() -> int:
    items: list[CheckItem] = []
    items.append(
        _check_import(
            "PySide6",
            required=False,
            reason="Overlay UI",
            hint="pip install PySide6",
        )
    )
    items.append(
        _check_import(
            "uiautomation",
            required=False,
            reason="UI Automation perception",
            hint="pip install uiautomation",
        )
    )
    items.append(
        _check_import(
            "keyboard",
            required=False,
            reason="Typing detection",
            hint="pip install keyboard",
        )
    )
    items.append(
        _check_import(
            "pytesseract",
            required=False,
            reason="OCR fallback",
            hint="pip install pytesseract",
        )
    )
    items.append(
        _check_import(
            "google.genai",
            required=False,
            reason="Gemini client",
            hint="pip install google-genai",
        )
    )
    items.append(
        _check_import(
            "websockets",
            required=True,
            reason="IPC server + overlay chat",
            hint="pip install websockets",
        )
    )

    start_overlay = os.getenv("START_OVERLAY_UI", "true").strip().lower() in {"1", "true", "yes", "on"}
    missing_required = [item for item in items if item.required and not item.ok]

    print("ScreenSense runtime check")
    print("-" * 32)
    for item in items:
        status = "OK" if item.ok else "MISSING"
        tag = "required" if item.required else "optional"
        if item.name == "PySide6" and not start_overlay:
            tag = "optional (overlay disabled)"
        print(f"{item.name:18} {status:9} {tag:24} {item.reason}")
        if not item.ok:
            print(f"  -> {item.hint}")

    if missing_required:
        print("\nOne or more required dependencies are missing.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
