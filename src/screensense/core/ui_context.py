from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

try:
    import uiautomation as auto
    UIA_AVAILABLE = True
except Exception:  # pragma: no cover
    UIA_AVAILABLE = False


@dataclass(slots=True)
class UiContextSettings:
    enabled: bool = True
    provider: Literal["uia", "none"] = "uia"
    min_interval_seconds: float = 2.0
    max_text_chars: int = 500


class UiContextExtractor:
    def __init__(self, settings: UiContextSettings | None = None) -> None:
        self._settings = settings or UiContextSettings()
        self._last_ts = 0.0
        self._last_context: dict[str, Any] = {}

    async def get_context(self) -> dict[str, Any]:
        now = time.time()
        if (now - self._last_ts) < self._settings.min_interval_seconds:
            return self._last_context
        ctx = self._extract()
        self._last_ts = now
        self._last_context = ctx
        return ctx

    def enrich(
        self,
        *,
        frame_rgb=None,
        app_context: dict[str, str | int | bool | None],
    ) -> dict[str, str | int | bool | None]:
        enriched = dict(app_context)
        # These fields are used by prompt builders and tests.
        enriched["ui_ocr_enabled"] = bool(self._settings.enabled)
        enriched["ui_ocr_provider"] = self._settings.provider
        if not self._settings.enabled or self._settings.provider == "none":
            return enriched
        ctx = self._extract()
        enriched["ui_context"] = ctx
        enriched["ui_text_excerpt"] = clean_ocr_text(
            json.dumps(ctx, ensure_ascii=True), max_chars=self._settings.max_text_chars
        )
        return enriched

    def _extract(self) -> dict[str, Any]:
        if not UIA_AVAILABLE or not self._settings.enabled:
            return {}
        try:
            window = auto.GetForegroundControl()
            if not window:
                return {}
            title = window.Name or ""
            process = window.ProcessName or ""

            result: dict[str, Any] = {
                "active_app": process,
                "window_title": title,
            }

            if "code" in process.lower():
                result.update(self._extract_vscode(window, title))
            elif any(
                b in process.lower() for b in ["chrome", "firefox", "msedge", "brave"]
            ):
                result.update(self._extract_browser(window))
            elif any(
                t in process.lower()
                for t in ["cmd", "powershell", "windowsterminal", "wt"]
            ):
                result.update(self._extract_terminal(window))
            else:
                result.update(self._extract_generic(window))
            return result
        except Exception as exc:
            return {"error": str(exc)[:100]}

    def _extract_vscode(self, window, title: str) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        parts = title.replace(" - Visual Studio Code", "").split(" - ")
        if parts:
            ctx["current_file"] = parts[0].strip()
        if len(parts) > 1:
            ctx["project"] = parts[1].strip()

        try:
            focused = auto.GetFocusedControl()
            if focused:
                ctx["focused_element"] = focused.ControlTypeName
                try:
                    sel = focused.GetSelectionText()
                    if sel and len(sel.strip()) > 2:
                        ctx["selected_text"] = sel.strip()[:300]
                except Exception:
                    pass
                try:
                    text = focused.Name or ""
                    if len(text) > 10:
                        ctx["visible_text"] = text[:400]
                except Exception:
                    pass

            try:
                editor_text = self._find_editor_text(window)
                if editor_text:
                    ctx["editor_content"] = editor_text[:500]
            except Exception:
                pass

            try:
                terminal_text = self._find_terminal_text(window)
                if terminal_text:
                    ctx["terminal_output"] = terminal_text[:300]
            except Exception:
                pass

            try:
                errors = self._find_errors(window)
                if errors:
                    ctx["errors"] = errors[:5]
            except Exception:
                pass
        except Exception as exc:
            ctx["extraction_note"] = str(exc)[:80]
        return ctx

    def _find_editor_text(self, window) -> str:
        texts: list[str] = []
        try:
            for ctrl in window.GetChildren():
                try:
                    if ctrl.ControlTypeName in ["EditControl", "DocumentControl"]:
                        t = ctrl.Name or ""
                        if len(t) > 20:
                            texts.append(t[:200])
                except Exception:
                    continue
        except Exception:
            pass
        return "\n".join(texts[:3])

    def _find_terminal_text(self, window) -> str:
        try:
            ctrls = window.GetChildren()
            for ctrl in ctrls:
                name = (ctrl.Name or "").lower()
                if "terminal" in name or "console" in name:
                    return (ctrl.Name or "")[:300]
        except Exception:
            pass
        return ""

    def _find_errors(self, window) -> list[str]:
        errors: list[str] = []
        try:
            ctrls = window.GetChildren()
            for ctrl in ctrls:
                name = ctrl.Name or ""
                if any(k in name.lower() for k in ["error", "warning", "problem"]):
                    errors.append(name[:100])
        except Exception:
            pass
        return errors

    def _extract_browser(self, window) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        title = window.Name or ""
        ctx["page_title"] = title
        try:
            focused = auto.GetFocusedControl()
            if focused and focused.ControlTypeName == "EditControl":
                url = focused.Name or focused.GetValuePattern()
                if url:
                    ctx["current_url"] = str(url)[:200]
        except Exception:
            pass
        try:
            sel = window.GetSelectionText()
            if sel:
                ctx["selected_text"] = sel[:200]
        except Exception:
            pass
        return ctx

    def _extract_terminal(self, window) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        try:
            focused = auto.GetFocusedControl()
            if focused:
                text = focused.Name or ""
                if text:
                    lines = text.strip().split("\n")
                    ctx["terminal_lines"] = lines[-20:]
                    ctx["last_command"] = lines[-1] if lines else ""
        except Exception:
            pass
        return ctx

    def _extract_generic(self, window) -> dict[str, Any]:
        ctx: dict[str, Any] = {}
        try:
            focused = auto.GetFocusedControl()
            if focused:
                ctx["focused_element_type"] = focused.ControlTypeName
                text = focused.Name or ""
                if text and len(text) > 2:
                    ctx["focused_text"] = text[:200]
            try:
                for child in window.GetChildren():
                    if child.ControlTypeName == "WindowControl":
                        ctx["dialog"] = child.Name[:100]
                        break
            except Exception:
                pass
        except Exception:
            pass
        return ctx


def clean_ocr_text(text: str, *, max_chars: int = 500) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if max_chars <= 0:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."
