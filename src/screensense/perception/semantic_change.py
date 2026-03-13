from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SemanticChange:
    score: float
    reasons: list[str]


def score_semantic_change(
    prev: dict[str, object] | None,
    curr: dict[str, object] | None,
) -> SemanticChange:
    prev = prev or {}
    curr = curr or {}
    reasons: list[str] = []
    score = 0.0

    def bump(value: float, reason: str) -> None:
        nonlocal score
        score = max(score, value)
        if reason not in reasons:
            reasons.append(reason)

    def text(key: str, source: dict[str, object]) -> str:
        val = source.get(key)
        if val is None:
            return ""
        return str(val).strip()

    def has_error_keywords(s: str) -> bool:
        lowered = s.lower()
        keywords = (
            "error",
            "exception",
            "traceback",
            "failed",
            "failure",
            "denied",
            "forbidden",
            "not found",
            "stack",
            "panic",
        )
        return any(k in lowered for k in keywords)

    if _changed(prev, curr, "active_app"):
        bump(1.0, "active_app_changed")
    if _changed(prev, curr, "window_title"):
        bump(0.8, "window_title_changed")
    if _changed(prev, curr, "error_list"):
        bump(0.8, "error_list_changed")
    if _changed(prev, curr, "terminal_exit_code"):
        bump(0.8, "terminal_exit_code_changed")
    if _changed(prev, curr, "any_dialog_text") or _changed(prev, curr, "any_popup_text"):
        bump(0.7, "dialog_or_popup_changed")
    if _changed(prev, curr, "any_notification_text"):
        bump(0.6, "notification_changed")
    if _changed(prev, curr, "current_file"):
        bump(0.6, "file_changed")
    if _cursor_jump(prev, curr, "cursor_line", threshold=20):
        bump(0.6, "cursor_jump")

    prev_terminal = text("terminal_last_output", prev) or text("last_output", prev) or text(
        "terminal_output", prev
    )
    curr_terminal = text("terminal_last_output", curr) or text("last_output", curr) or text(
        "terminal_output", curr
    )
    if prev_terminal != curr_terminal and curr_terminal:
        bump(0.45, "terminal_changed")
        if has_error_keywords(curr_terminal) and not has_error_keywords(prev_terminal):
            bump(1.0, "terminal_error_detected")

    prev_errors = text("error_list", prev) or text("errors", prev)
    curr_errors = text("error_list", curr) or text("errors", curr)
    if curr_errors and not prev_errors:
        bump(1.0, "new_errors_detected")

    if score == 0.0:
        score = 0.2 if _minor_changes(prev, curr) else 0.0
        if score > 0.0:
            reasons.append("minor_change")

    return SemanticChange(score=score, reasons=reasons)


def _changed(prev: dict[str, object], curr: dict[str, object], key: str) -> bool:
    return (prev.get(key) or "") != (curr.get(key) or "")


def _cursor_jump(
    prev: dict[str, object],
    curr: dict[str, object],
    key: str,
    threshold: int,
) -> bool:
    try:
        prev_val = int(prev.get(key) or 0)
        curr_val = int(curr.get(key) or 0)
    except (TypeError, ValueError):
        return False
    return abs(curr_val - prev_val) > threshold


def _minor_changes(prev: dict[str, object], curr: dict[str, object]) -> bool:
    keys = {"focused_element_text", "focused_input_value", "ui_text_excerpt"}
    for key in keys:
        if _changed(prev, curr, key):
            return True
    return False
