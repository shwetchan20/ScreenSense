from __future__ import annotations

import os
import re
from pathlib import Path


TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line (\d+)')
EXCEPTION_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Interrupt))")


class CodingHelper:
    def analyze(self, *, screen_context: dict) -> dict:
        active_app = str(screen_context.get("active_app", "")).lower()
        window_title = str(screen_context.get("window_title", "")).lower()
        focused_type = str(screen_context.get("uia_focused_control_type", "")).lower()
        if not any(token in active_app for token in ("code.exe", "python.exe", "windowsterminal.exe", "cmd.exe")):
            if not any(token in window_title for token in ("visual studio code", "terminal", "powershell", "python")):
                return {"is_coding_context": False}

        text_candidates = self._collect_text_candidates(screen_context)
        file_hits = self._extract_file_hits(text_candidates)
        exception_names = self._extract_exception_names(text_candidates)

        if not text_candidates and not file_hits and not exception_names and "editcontrol" not in focused_type:
            return {"is_coding_context": False}

        primary_exception = exception_names[0] if exception_names else ""
        primary_file = file_hits[0]["path"] if file_hits else ""
        primary_line = file_hits[0]["line"] if file_hits else 0
        code_snippet = self._read_snippet(primary_file, primary_line) if primary_file and primary_line else ""
        diagnosis = self._heuristic_diagnosis(primary_exception, text_candidates)
        suggestion = self._heuristic_suggestion(primary_exception, diagnosis, primary_file, primary_line, code_snippet)

        return {
            "is_coding_context": True,
            "has_error": bool(primary_exception or file_hits),
            "primary_exception": primary_exception,
            "primary_file": primary_file,
            "primary_line": primary_line,
            "traceback_files": file_hits[:6],
            "diagnosis": diagnosis,
            "suggestion": suggestion,
            "code_snippet": code_snippet,
        }

    @staticmethod
    def _collect_text_candidates(screen_context: dict) -> list[str]:
        chunks: list[str] = []
        for key in (
            "uia_focused_text",
            "detailed_description",
            "visible_content_summary",
            "current_content",
            "page_summary",
        ):
            value = str(screen_context.get(key, "")).strip()
            if value:
                chunks.append(value)

        for item in screen_context.get("window_visible_text_summary", []):
            text = str(item).strip()
            if text:
                chunks.append(text)

        for item in screen_context.get("window_visible_text", []):
            text = str(item).strip()
            if text:
                chunks.append(text)

        for item in screen_context.get("visible_text", []):
            text = str(item).strip()
            if text:
                chunks.append(text)
        return chunks

    @staticmethod
    def _extract_file_hits(text_candidates: list[str]) -> list[dict]:
        hits: list[dict] = []
        seen: set[tuple[str, int]] = set()
        for chunk in text_candidates:
            for match in TRACEBACK_FILE_RE.finditer(chunk):
                path = match.group(1).strip()
                line = int(match.group(2))
                key = (path.lower(), line)
                if key in seen:
                    continue
                seen.add(key)
                hits.append({"path": path, "line": line})
        return hits

    @staticmethod
    def _extract_exception_names(text_candidates: list[str]) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for chunk in text_candidates:
            for match in EXCEPTION_RE.finditer(chunk):
                name = match.group(1)
                lowered = name.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                names.append(name)
        return names

    @staticmethod
    def _read_snippet(path_str: str, line_number: int) -> str:
        path = Path(path_str)
        if not path.exists():
            return ""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                return ""
        start = max(0, line_number - 3)
        end = min(len(lines), line_number + 2)
        snippet_lines = []
        for idx in range(start, end):
            snippet_lines.append(f"{idx + 1}: {lines[idx]}")
        return "\n".join(snippet_lines)

    @staticmethod
    def _heuristic_diagnosis(primary_exception: str, text_candidates: list[str]) -> str:
        full_text = "\n".join(text_candidates).lower()
        if primary_exception == "KeyboardInterrupt" and "cancellederror" in full_text:
            return "The async program was interrupted by the user, which caused pending tasks to be cancelled."
        if primary_exception == "CancelledError":
            return "An asyncio task was cancelled before it completed."
        if primary_exception == "KeyError":
            return "Code is trying to access a missing key or field in a dict-like object."
        if primary_exception == "AttributeError":
            return "Code is trying to use an attribute or method that does not exist on the object."
        if primary_exception == "TypeError":
            return "Code is using a value with the wrong type or calling a function with incompatible arguments."
        if primary_exception == "ValueError":
            return "Code received a value that has the right type but an invalid content or format."
        if primary_exception:
            return f"The screen shows a {primary_exception} traceback in the coding environment."
        if "traceback" in full_text:
            return "The screen shows a Python traceback in the coding environment."
        return "The screen appears to show a coding or terminal context."

    @staticmethod
    def _heuristic_suggestion(
        primary_exception: str,
        diagnosis: str,
        primary_file: str,
        primary_line: int,
        code_snippet: str,
    ) -> str:
        location = ""
        if primary_file and primary_line:
            location = f"Check {os.path.basename(primary_file)}:{primary_line} first."

        if primary_exception == "KeyboardInterrupt":
            return (
                f"{location} This looks like a manual stop rather than a real bug. "
                "If you want cleaner shutdown output, catch KeyboardInterrupt around asyncio.run() and handle asyncio.CancelledError during cleanup."
            ).strip()
        if primary_exception == "CancelledError":
            return (
                f"{location} Look for task cancellation, shutdown logic, or awaited locks/events that are being interrupted. "
                "If cancellation is expected, catch asyncio.CancelledError during shutdown and re-raise after cleanup."
            ).strip()
        if primary_exception == "KeyError":
            return (
                f"{location} Verify the dict keys being accessed and inspect the incoming payload/context before the failing line."
            ).strip()
        if primary_exception == "AttributeError":
            return (
                f"{location} Inspect the object type at the failing line and confirm the attribute or method actually exists."
            ).strip()
        if primary_exception:
            return f"{location} {diagnosis}".strip()
        if code_snippet:
            return f"{location} Inspect the surrounding code shown below and compare it with the traceback."
        return diagnosis
