from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from screensense.core.window_context import get_active_window_context

try:
    import uiautomation as uia
except Exception:  # pragma: no cover
    uia = None  # type: ignore[assignment]


@dataclass(slots=True)
class UiContextResult:
    ok: bool
    context: dict[str, Any]
    text: str


class UiAutomationContext:
    def __init__(self) -> None:
        self._last_context: dict[str, Any] = {}
        self._last_vscode_clipboard_ts = 0.0

    def capture(self) -> UiContextResult:
        active = get_active_window_context()
        context: dict[str, Any] = {
            "active_app": active.process_name or "",
            "window_title": active.title or "",
        }
        if uia is None:
            self._fallback_vscode_context(context)
            return UiContextResult(ok=False, context=context, text=self._compact_text(context))

        try:
            focused = uia.GetFocusedControl()
        except Exception:
            focused = None

        if focused is not None:
            context["focused_element_type"] = getattr(focused, "ControlTypeName", "") or ""
            context["focused_element_text"] = _first_non_empty(
                _safe_get(focused, "Name"),
                _safe_get(focused, "Value"),
            )
            value = _safe_get(focused, "Value")
            if value:
                context["focused_input_value"] = value

        app_key = (active.process_name or "").lower()
        title = (active.title or "").lower()
        is_ide = any(token in app_key or token in title for token in ("code", "pycharm", "idea", "sublime"))
        is_browser = any(token in app_key for token in ("chrome", "edge", "brave", "firefox"))
        is_terminal = any(token in app_key for token in ("terminal", "cmd", "powershell", "windows terminal"))

        if is_ide:
            self._enrich_ide(context, focused)
        if is_browser:
            self._enrich_browser(context, focused)
        if is_terminal:
            self._enrich_terminal(context, focused)
        if is_ide:
            self._fallback_vscode_context(context)

        # Generic dialog / notification heuristics.
        dialog_text = self._find_dialog_text(active.title or "")
        if dialog_text:
            context["any_dialog_text"] = dialog_text

        notification_text = self._find_notification_text()
        if notification_text:
            context["any_notification_text"] = notification_text

        clean = _strip_empty(context)
        text = self._compact_text(clean)
        return UiContextResult(ok=bool(clean), context=clean, text=text)

    def _fallback_vscode_context(self, context: dict[str, Any]) -> None:
        if context.get("current_file"):
            return
        title = str(context.get("window_title") or "")
        if not title:
            return
        lowered = title.lower()
        if "visual studio code" not in lowered and "code" not in lowered:
            return
        file_name, project = _parse_vscode_title(title)
        if file_name:
            context["current_file"] = file_name
        if project:
            context["project"] = project

    def _enrich_ide(self, context: dict[str, Any], focused) -> None:
        title = context.get("window_title", "")
        file_match = re.search(r"([\\w.\\-]+\\.(py|js|ts|tsx|jsx|java|cs|cpp|c|go|rs|rb|php))", title)
        if file_match:
            context["current_file"] = file_match.group(1)
        status = self._find_status_bar_text()
        if status:
            line_col = _parse_line_col(status)
            if line_col:
                context["cursor_line"] = line_col[0]
                context["cursor_column"] = line_col[1]
        visible_text = _safe_get(focused, "Value") if focused is not None else ""
        if visible_text:
            context["visible_code"] = _truncate_lines(visible_text, max_lines=10)
        else:
            # Optional, off-by-default: clipboard fallback for Monaco-based editors.
            # Enable with ENABLE_VSCODE_CLIPBOARD_READ=true.
            if self._clipboard_read_enabled(context):
                excerpt = self._try_vscode_clipboard_excerpt()
                if excerpt:
                    context["visible_code"] = excerpt

        errors = self._find_error_list()
        if errors:
            context["error_list"] = errors

        terminal_output = self._find_terminal_output()
        if terminal_output:
            context["terminal_last_output"] = terminal_output
            context["terminal_error_hint"] = _error_hint(terminal_output)

    def _enrich_browser(self, context: dict[str, Any], focused) -> None:
        title = context.get("window_title", "")
        if title:
            context["page_title"] = title
        selected = _safe_get(focused, "Value")
        if selected:
            context["selected_text"] = selected
        headings = self._find_headings()
        if headings:
            context["visible_headings"] = headings

    def _enrich_terminal(self, context: dict[str, Any], focused) -> None:
        text = _safe_get(focused, "Value") if focused is not None else ""
        if text:
            lines = _safe_tail_lines(text, 20)
            context["last_output"] = lines
            last_cmd = _infer_last_command(lines)
            if last_cmd:
                context["last_command"] = last_cmd

    def _find_status_bar_text(self) -> str:
        if uia is None:
            return ""
        try:
            root = uia.GetRootControl()
            for ctrl in root.GetChildren():
                name = getattr(ctrl, "Name", "") or ""
                if "status" in name.lower():
                    return name
        except Exception:
            return ""
        return ""

    def _find_error_list(self) -> str:
        if uia is None:
            return ""
        try:
            root = uia.GetRootControl()
            texts = []
            for ctrl in root.GetChildren():
                name = getattr(ctrl, "Name", "") or ""
                if "error" in name.lower() or "warning" in name.lower():
                    texts.append(name)
            return _compact_lines(texts, max_chars=160)
        except Exception:
            return ""

    def _find_terminal_output(self) -> str:
        if uia is None:
            return ""
        try:
            focused = uia.GetFocusedControl()
            value = _safe_get(focused, "Value")
            if value:
                return _safe_tail_lines(value, 15)
        except Exception:
            return ""
        return ""

    def _find_headings(self) -> str:
        if uia is None:
            return ""
        try:
            root = uia.GetRootControl()
            headings = []
            for ctrl in root.GetChildren():
                name = getattr(ctrl, "Name", "") or ""
                if name.strip() and len(name.split()) <= 6:
                    headings.append(name.strip())
            return _compact_lines(headings, max_chars=140)
        except Exception:
            return ""

    def _find_dialog_text(self, window_title: str) -> str:
        if not window_title:
            return ""
        if any(token in window_title.lower() for token in ("error", "warning", "failed")):
            return window_title
        return ""

    def _find_notification_text(self) -> str:
        if uia is None:
            return ""
        # Best-effort: scan a small slice of root children for toast-like text.
        try:
            root = uia.GetRootControl()
            snippets: list[str] = []
            for ctrl in root.GetChildren()[:40]:
                name = getattr(ctrl, "Name", "") or ""
                lowered = name.lower()
                if not name.strip():
                    continue
                if any(token in lowered for token in ("notification", "toast", "warning", "error")):
                    snippets.append(name.strip())
            return _compact_lines(snippets, max_chars=160)
        except Exception:
            return ""

    def _clipboard_read_enabled(self, context: dict[str, Any]) -> bool:
        enabled = os.getenv("ENABLE_VSCODE_CLIPBOARD_READ", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return False
        title = str(context.get("window_title") or "").lower()
        app = str(context.get("active_app") or "").lower()
        return ("visual studio code" in title) or ("code" in app)

    def _try_vscode_clipboard_excerpt(self) -> str:
        import time

        now = time.time()
        if (now - self._last_vscode_clipboard_ts) < 10.0:
            return ""
        self._last_vscode_clipboard_ts = now

        try:
            import pyperclip
        except Exception:
            return ""
        try:
            import keyboard as kb
        except Exception:
            return ""

        try:
            old = pyperclip.paste()
            # Select-all and copy; this is intrusive (selection changes), hence opt-in.
            kb.send("ctrl+a")
            time.sleep(0.06)
            kb.send("ctrl+c")
            time.sleep(0.12)
            text = pyperclip.paste() or ""
            try:
                pyperclip.copy(old)
            except Exception:
                pass
            text = str(text).strip()
            if not text:
                return ""
            return _truncate_lines(text, max_lines=14)[:800]
        except Exception:
            return ""

    def _compact_text(self, context: dict[str, Any]) -> str:
        if not context:
            return ""
        compact = json.dumps(context, ensure_ascii=True, separators=(",", ":"))
        if len(compact) <= 500:
            return compact
        return compact[:497] + "..."


def _safe_get(control, attr: str) -> str:
    try:
        value = getattr(control, attr, "")
        if value is None:
            return ""
        return str(value).strip()
    except Exception:
        return ""


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _strip_empty(data: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, tuple)) and not value:
            continue
        cleaned[key] = value
    return cleaned


def _parse_line_col(text: str) -> tuple[int, int] | None:
    match = re.search(r"Ln\\s*(\\d+)[^0-9]+Col\\s*(\\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _truncate_lines(text: str, *, max_lines: int) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def _safe_tail_lines(text: str, count: int) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[-count:])


def _compact_lines(lines: list[str], *, max_chars: int) -> str:
    merged = "; ".join([line.strip() for line in lines if line.strip()])
    if len(merged) <= max_chars:
        return merged
    return merged[: max_chars - 3] + "..."


def _infer_last_command(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    last = lines[-1]
    if last.startswith(">"):
        return last.lstrip(">").strip()
    return ""


def _parse_vscode_title(title: str) -> tuple[str, str]:
    # Example: ".env - screensense - Visual Studio Code"
    parts = [part.strip() for part in title.split(" - ") if part.strip()]
    file_name = ""
    project = ""
    if len(parts) >= 3 and "visual studio code" in parts[-1].lower():
        file_name = parts[0]
        project = parts[1]
    elif len(parts) >= 2 and "visual studio code" in parts[-1].lower():
        file_name = parts[0]
    return file_name, project


def _error_hint(text: str) -> str:
    lowered = (text or "").lower()
    tokens = ("error", "exception", "traceback", "failed", "denied", "forbidden", "not found")
    for t in tokens:
        idx = lowered.find(t)
        if idx >= 0:
            start = max(0, idx - 24)
            end = min(len(text), idx + 120)
            return re.sub(r"\s+", " ", text[start:end]).strip()
    return ""
