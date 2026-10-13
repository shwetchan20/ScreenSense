from __future__ import annotations

import asyncio
import io
import json
import os
from collections import deque
from datetime import datetime, timezone

import mss
import psutil
import uiautomation as auto
import win32gui
import win32process
from PIL import Image

from aria.config import OLLAMA_URL, SCREENSHOT_FORMAT, VLM_MODEL
from aria.perception.vlm_client import VLMClient

MAX_VISIBLE_TEXT = int(os.environ.get("ARIA_SCREEN_MAX_VISIBLE_TEXT", "4"))
MAX_INTERACTABLE = int(os.environ.get("ARIA_SCREEN_MAX_INTERACTABLE", "2"))
SCREENSHOT_MAX_WIDTH = int(os.environ.get("ARIA_SCREENSHOT_MAX_WIDTH", "960"))
SCREENSHOT_MAX_HEIGHT = int(os.environ.get("ARIA_SCREENSHOT_MAX_HEIGHT", "540"))
SCREEN_VLM_NUM_PREDICT = int(os.environ.get("ARIA_SCREEN_VLM_NUM_PREDICT", "384"))
SCREEN_VLM_TIMEOUT_SECONDS = float(os.environ.get("ARIA_SCREEN_VLM_TIMEOUT_SECONDS", "180"))


SCREEN_UNDERSTANDING_PROMPT = """
You are a screen analysis engine. Analyze the screenshot and respond in plain text using this exact format.
Do not use JSON. Do not use markdown. Do not add any extra headings.

SCREEN_STATE: one of idle, loading, error, form, video, dialog, desktop
PAGE_SUMMARY: short user-facing summary of what the person is currently looking at
CURRENT_CONTENT: one sentence about the main content area
DETAIL: concise but information-dense paragraph describing what is visible on screen
LAYOUT: one sentence describing the screen layout
VISIBLE_TEXT: up to 4 important visible text snippets separated by | characters

Rules:
- focus on what is visually obvious and most relevant
- never copy these instructions into the answer
- if uncertain, keep the field short instead of inventing details
- VISIBLE_TEXT must contain short snippets, not full paragraphs
""".strip()

RICH_REPORT_PROMPT = """
You are writing a grounded desktop screen report for a coding assistant.
Use ONLY the provided facts. Do not guess missing details. Do not invent browser results, code errors, or app state.
If a detail is missing from the facts, leave that field short, empty, or use "unknown".

Return plain text in exactly this format:
FOCUSED_WINDOW: one short line
CURRENT_VIEW: one or two sentences about what the person is doing
VISIBLE_CONTENT: two to four sentences with concrete visible details grounded in the facts
BROWSER_TABS: titles separated by | characters
OTHER_RUNNING_APPS: app names separated by | characters
FINAL_STATE: one short concluding sentence

Facts:
{facts_json}
""".strip()


class ScreenContextCollector:
    def __init__(self, *, vlm: VLMClient) -> None:
        self._vlm = vlm

    async def capture_screenshot(self) -> tuple[bytes, tuple[int, int]]:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            image.thumbnail((SCREENSHOT_MAX_WIDTH, SCREENSHOT_MAX_HEIGHT))
            buf = io.BytesIO()
            image.save(buf, format=SCREENSHOT_FORMAT)
            return buf.getvalue(), (image.width, image.height)

    async def get_vlm_context(self, image_bytes: bytes) -> dict:
        if os.environ.get("ARIA_PERCEPTION_MODE", "text_grounded").strip().lower() == "text_grounded":
            return {
                "screen_state": "desktop",
                "visible_text": [],
                "interactable_elements": [],
                "layout_description": "desktop workspace",
                "current_content": "active desktop workspace",
                "detailed_description": "active desktop workspace",
                "page_summary": "desktop workspace",
            }
        response_text = await self._vlm.generate_text(
            SCREEN_UNDERSTANDING_PROMPT,
            image_bytes=image_bytes,
            num_predict=SCREEN_VLM_NUM_PREDICT,
            timeout_seconds=SCREEN_VLM_TIMEOUT_SECONDS,
        )
        return self._parse_vlm_text_response(response_text)


    def get_uia_context(self) -> dict:
        with auto.UIAutomationInitializerInThread():
            tabs = []
            focused_control = auto.GetFocusedControl()
            focused_name = focused_control.Name if focused_control else ""
            focused_text = focused_name
            focused_control_type = focused_control.ControlTypeName if focused_control else ""
            focused_window = auto.GetForegroundControl()
            uia_elements: list[dict[str, object]] = []
            window_visible_text: list[str] = []
            browser_context = {
                "browser_address_text": "",
                "browser_page_text": [],
                "window_visible_text": [],
            }

            root = auto.GetRootControl()
            browser_windows = []
            for c in root.GetChildren():
                try:
                    control_type = c.ControlTypeName
                    control_name = (c.Name or "").lower()
                except Exception:
                    continue
                if control_type == "WindowControl" and any(
                    k in control_name for k in ("chrome", "edge", "firefox", "brave")
                ):
                    browser_windows.append(c)

            tab_idx = 0
            for win in browser_windows:
                try:
                    candidates = win.GetChildren()
                except Exception:
                    continue
                for child in candidates:
                    try:
                        child_type = child.ControlTypeName
                    except Exception:
                        continue
                    if child_type in {"TabControl", "ToolBarControl"}:
                        try:
                            children = child.GetChildren()
                        except Exception:
                            continue
                        for item in children:
                            try:
                                item_type = item.ControlTypeName
                            except Exception:
                                continue
                            if item_type in {"TabItemControl", "ButtonControl"}:
                                try:
                                    title = (item.Name or "").strip()
                                    active = bool(item.HasKeyboardFocus)
                                except Exception:
                                    continue
                                if title:
                                    bbox, center = self._safe_rect(item)
                                    tabs.append(
                                        {
                                            "index": tab_idx,
                                            "title": title,
                                            "url": "",
                                            "active": active,
                                            "bbox": bbox,
                                            "center": center,
                                        }
                                    )
                                    tab_idx += 1

            if focused_window is not None:
                uia_elements = self._extract_uia_elements(focused_window)
                browser_context = self._extract_browser_context(focused_window)
                window_visible_text = self._extract_window_visible_text(focused_window)
                if window_visible_text:
                    browser_context["window_visible_text"] = window_visible_text

            return {
                "browser_tabs": tabs,
                "uia_focused_element": focused_name,
                "uia_focused_text": focused_text,
                "uia_focused_control_type": focused_control_type,
                "uia_interactable_elements": uia_elements,
                **browser_context,
            }

    def get_win32_context(self) -> dict:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid < 0:
            pid = pid & 0xFFFFFFFF
        try:
            process_name = psutil.Process(pid).name() if pid > 0 else ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            process_name = ""

        windows: list[dict[str, str]] = []

        def enum_cb(h: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(h):
                return True
            window_title = win32gui.GetWindowText(h).strip()
            if not window_title:
                return True
            try:
                _, window_pid = win32process.GetWindowThreadProcessId(h)
                if window_pid < 0:
                    window_pid = window_pid & 0xFFFFFFFF
                proc_name = psutil.Process(window_pid).name() if window_pid > 0 else ""
                windows.append({"process": proc_name, "title": window_title})
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                pass
            return True

        try:
            win32gui.EnumWindows(enum_cb, 0)
        except Exception:
            pass
        return {
            "active_app": process_name,
            "window_title": title,
            "all_windows": windows,
        }

    async def get_unified_screen_context(self) -> dict:
        image_bytes, resolution = await self.capture_screenshot()
        vlm_task = asyncio.create_task(self.get_vlm_context(image_bytes))
        uia_task = asyncio.get_running_loop().run_in_executor(None, self.get_uia_context)
        win32_task = asyncio.get_running_loop().run_in_executor(None, self.get_win32_context)
        vlm_result, uia_result, win32_result = await asyncio.gather(vlm_task, uia_task, win32_task)
        normalized_vlm_result = self._normalize_vlm_result(vlm_result, resolution)
        context = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **win32_result,
            **uia_result,
            **normalized_vlm_result,
            "screen_resolution": [resolution[0], resolution[1]],
        }
        context["actionable_context"] = self._build_actionable_context(context)
        context["interactable_elements"] = list(context["actionable_context"]["interactable_elements"])
        context.update(self._build_report_fields(context))
        context.update(await self._synthesize_rich_report(context))
        return context

    @staticmethod
    def _normalize_vlm_result(vlm_result: dict, resolution: tuple[int, int]) -> dict:
        width, height = resolution
        placeholder_fragments = (
            "most important readable text strings",
            "exact text or description",
            "one sentence describing spatial layout",
            "what the main content area is showing",
            "screen_state:",
            "page_summary:",
        )

        visible_text: list[str] = []
        seen_text: set[str] = set()
        for item in vlm_result.get("visible_text", []):
            text = str(item).strip()
            lowered = text.lower()
            if not text:
                continue
            if any(fragment in lowered for fragment in placeholder_fragments):
                continue
            if lowered in seen_text:
                continue
            seen_text.add(lowered)
            visible_text.append(text)

        interactable_elements: list[dict] = []
        seen_elements: set[tuple[str, tuple[int, int, int, int]]] = set()
        for item in vlm_result.get("interactable_elements", []):
            bbox = tuple(int(v) for v in item.get("bbox", []))
            center = tuple(int(v) for v in item.get("center", []))
            if len(bbox) != 4 or len(center) != 2:
                continue
            x1, y1, x2, y2 = bbox
            cx, cy = center
            if x2 <= x1 or y2 <= y1:
                continue
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
                continue
            if cx < 0 or cy < 0 or cx > width or cy > height:
                continue
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            key = (label.lower(), bbox)
            if key in seen_elements:
                continue
            seen_elements.add(key)
            interactable_elements.append(
                {
                    "id": int(item["id"]),
                    "type": str(item["type"]),
                    "label": label,
                    "bbox": [x1, y1, x2, y2],
                    "center": [cx, cy],
                    "state": str(item["state"]),
                }
            )

        return {
            "screen_state": str(vlm_result.get("screen_state", "idle")).strip(),
            "visible_text": visible_text,
            "interactable_elements": interactable_elements,
            "layout_description": str(vlm_result.get("layout_description", "")).strip(),
            "current_content": str(vlm_result.get("current_content", "")).strip(),
            "detailed_description": str(vlm_result.get("detailed_description", "")).strip(),
            "page_summary": str(vlm_result.get("page_summary", "")).strip(),
        }

    @staticmethod
    def _parse_vlm_text_response(response_text: str) -> dict:
        parsed: dict[str, str] = {}
        current_key = ""
        for line in response_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                current_key = key.strip().upper()
                parsed[current_key] = value.strip()
                continue
            if current_key:
                parsed[current_key] = f"{parsed[current_key]} {stripped}".strip()

        visible_text_field = parsed.get("VISIBLE_TEXT", "")
        visible_text = [
            item.strip()
            for item in visible_text_field.split("|")
            if item.strip()
        ][:MAX_VISIBLE_TEXT]

        screen_state = parsed.get("SCREEN_STATE", "idle").strip().lower()
        if screen_state not in {"idle", "loading", "error", "form", "video", "dialog", "desktop"}:
            screen_state = "idle"

        return {
            "screen_state": screen_state,
            "visible_text": visible_text,
            "interactable_elements": [],
            "layout_description": parsed.get("LAYOUT", ""),
            "current_content": ScreenContextCollector._clean_summary_text(parsed.get("CURRENT_CONTENT", "")),
            "detailed_description": ScreenContextCollector._clean_summary_text(parsed.get("DETAIL", "")),
            "page_summary": ScreenContextCollector._clean_summary_text(parsed.get("PAGE_SUMMARY", "")),
        }

    @staticmethod
    def _safe_rect(control: object) -> tuple[list[int], list[int]]:
        try:
            rect = control.BoundingRectangle
            left = int(rect.left)
            top = int(rect.top)
            right = int(rect.right)
            bottom = int(rect.bottom)
        except Exception:
            return [], []
        if right <= left or bottom <= top:
            return [], []
        bbox = [left, top, right, bottom]
        center = [int((left + right) / 2), int((top + bottom) / 2)]
        return bbox, center

    @staticmethod
    def _map_control_type(control_type_name: str) -> str | None:
        mapping = {
            "ButtonControl": "button",
            "EditControl": "input",
            "HyperlinkControl": "link",
            "ComboBoxControl": "dropdown",
            "CheckBoxControl": "checkbox",
            "TabItemControl": "tab",
            "MenuItemControl": "button",
            "ListItemControl": "button",
            "DocumentControl": None,
            "PaneControl": None,
            "WindowControl": None,
            "TextControl": None,
        }
        return mapping.get(control_type_name, "button")

    def _extract_uia_elements(self, root_control: object) -> list[dict[str, object]]:
        elements: list[dict[str, object]] = []
        queue: deque[tuple[object, int]] = deque([(root_control, 0)])
        next_id = 1
        max_depth = 4
        max_elements = 14

        while queue and len(elements) < max_elements:
            control, depth = queue.popleft()
            if depth > max_depth:
                continue
            try:
                children = control.GetChildren()
            except Exception:
                continue
            for child in children:
                try:
                    control_type_name = child.ControlTypeName
                    label = (child.Name or "").strip()
                    has_focus = bool(child.HasKeyboardFocus)
                    enabled = bool(child.IsEnabled)
                except Exception:
                    continue
                mapped_type = self._map_control_type(control_type_name)
                bbox, center = self._safe_rect(child)
                if mapped_type is not None and label and bbox and center:
                    state = "focused" if has_focus else ("enabled" if enabled else "disabled")
                    elements.append(
                        {
                            "id": next_id,
                            "type": mapped_type,
                            "label": label,
                            "bbox": bbox,
                            "center": center,
                            "state": state,
                            "source": "uia",
                        }
                    )
                    next_id += 1
                    if len(elements) >= max_elements:
                        break
                if depth < max_depth:
                    queue.append((child, depth + 1))
        return elements

    def _extract_browser_context(self, root_control: object) -> dict:
        address_text = ""
        page_text: list[str] = []
        window_text: list[str] = []
        queue: deque[tuple[object, int]] = deque([(root_control, 0)])
        max_depth = 5
        seen_text: set[str] = set()

        while queue:
            control, depth = queue.popleft()
            if depth > max_depth:
                continue
            try:
                children = control.GetChildren()
            except Exception:
                continue
            for child in children:
                try:
                    control_type_name = child.ControlTypeName
                    name = (child.Name or "").strip()
                    value_pattern = child.GetValuePattern()
                    value_text = value_pattern.Value.strip() if value_pattern is not None and value_pattern.Value else ""
                except Exception:
                    value_text = ""
                    try:
                        control_type_name = child.ControlTypeName
                        name = (child.Name or "").strip()
                    except Exception:
                        continue

                candidate_text = value_text or name
                lowered = candidate_text.lower()

                if control_type_name == "EditControl" and candidate_text and not address_text:
                    if any(token in lowered for token in ("http", "www.", ".com", ".org", "search", "brave", "google")):
                        address_text = candidate_text

                if control_type_name in {"TextControl", "DocumentControl", "HyperlinkControl"} and candidate_text:
                    if len(candidate_text) > 2 and lowered not in seen_text:
                        seen_text.add(lowered)
                        page_text.append(candidate_text)
                        window_text.append(candidate_text)
                        if len(page_text) >= 8:
                            return {
                                "browser_address_text": address_text,
                                "browser_page_text": page_text,
                                "window_visible_text": window_text,
                            }
                elif control_type_name in {"EditControl", "ListItemControl"} and candidate_text:
                    if len(candidate_text) > 2 and lowered not in seen_text:
                        seen_text.add(lowered)
                        window_text.append(candidate_text)

                if depth < max_depth:
                    queue.append((child, depth + 1))

        return {
            "browser_address_text": address_text,
            "browser_page_text": page_text,
                "window_visible_text": window_text,
            }

    @staticmethod
    def _extract_window_visible_text(root_control: object) -> list[str]:
        snippets: list[str] = []
        seen: set[str] = set()
        queue: deque[tuple[object, int]] = deque([(root_control, 0)])
        max_depth = 5
        max_items = 20

        while queue and len(snippets) < max_items:
            control, depth = queue.popleft()
            if depth > max_depth:
                continue
            try:
                children = control.GetChildren()
            except Exception:
                continue
            for child in children:
                try:
                    control_type_name = child.ControlTypeName
                    name = (child.Name or "").strip()
                    value_pattern = child.GetValuePattern()
                    value_text = value_pattern.Value.strip() if value_pattern is not None and value_pattern.Value else ""
                except Exception:
                    continue

                candidate_text = value_text or name
                lowered = candidate_text.lower()
                if not candidate_text or len(candidate_text) < 2:
                    if depth < max_depth:
                        queue.append((child, depth + 1))
                    continue

                if control_type_name in {
                    "TextControl",
                    "DocumentControl",
                    "EditControl",
                    "ListItemControl",
                    "ButtonControl",
                    "HyperlinkControl",
                    "PaneControl",
                    "TabItemControl",
                    "ComboBoxControl",
                    "CheckBoxControl",
                } and lowered not in seen:
                    seen.add(lowered)
                    snippets.append(candidate_text)

                if depth < max_depth:
                    queue.append((child, depth + 1))

        return snippets

    @staticmethod
    def _build_actionable_context(context: dict) -> dict:
        merged: list[dict[str, object]] = []
        seen_keys: set[tuple[str, tuple[int, int, int, int]]] = set()
        next_id = 1

        def add_elements(source_elements: list[dict]) -> None:
            nonlocal next_id
            for item in source_elements:
                bbox = tuple(int(v) for v in item.get("bbox", []))
                center = [int(v) for v in item.get("center", [])]
                label = str(item.get("label", "")).strip()
                if len(bbox) != 4 or len(center) != 2 or not label:
                    continue
                key = (label.lower(), bbox)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged.append(
                    {
                        "id": next_id,
                        "type": str(item.get("type", "button")),
                        "label": label,
                        "bbox": list(bbox),
                        "center": center,
                        "state": str(item.get("state", "enabled")),
                    }
                )
                next_id += 1

        add_elements(list(context.get("uia_interactable_elements", [])))
        tab_elements = []
        for tab in context.get("browser_tabs", []):
            bbox = tab.get("bbox", [])
            center = tab.get("center", [])
            title = str(tab.get("title", "")).strip()
            if bbox and center and title:
                tab_elements.append(
                    {
                        "type": "tab",
                        "label": title,
                        "bbox": bbox,
                        "center": center,
                        "state": "focused" if bool(tab.get("active")) else "enabled",
                    }
                )
        add_elements(tab_elements)
        add_elements(list(context.get("interactable_elements", [])))

        return {
            "interactable_elements": merged[:16],
            "uia_focused_element": str(context.get("uia_focused_element", "")).strip(),
        }

    @staticmethod
    def _build_report_fields(context: dict) -> dict:
        active_app = str(context.get("active_app", "")).strip()
        window_title = str(context.get("window_title", "")).strip()
        current_content = str(context.get("current_content", "")).strip()
        detailed_description = str(context.get("detailed_description", "")).strip()
        page_summary = str(context.get("page_summary", "")).strip()
        browser_tabs = list(context.get("browser_tabs", []))
        browser_address_text = str(context.get("browser_address_text", "")).strip()
        browser_page_text = list(context.get("browser_page_text", []))
        window_visible_text = list(context.get("window_visible_text", []))
        all_windows = list(context.get("all_windows", []))

        active_tab = next((tab for tab in browser_tabs if bool(tab.get("active"))), None)
        active_tab_title = str(active_tab.get("title", "")).strip() if active_tab else ""
        focused_window_summary = f"{window_title} ({active_app})".strip()

        current_task_summary = page_summary or current_content or detailed_description
        if browser_address_text and not current_task_summary:
            current_task_summary = browser_address_text
        current_task_summary = ScreenContextCollector._clean_summary_text(current_task_summary)
        if active_tab_title and current_task_summary:
            current_task_summary = f"{active_tab_title}: {current_task_summary}"
        elif active_tab_title:
            current_task_summary = active_tab_title

        browser_tabs_summary: list[str] = []
        seen_titles: set[str] = set()
        for tab in browser_tabs:
            title = str(tab.get("title", "")).strip()
            lowered = title.lower()
            if not title or lowered in seen_titles:
                continue
            seen_titles.add(lowered)
            browser_tabs_summary.append(title)

        other_running_apps_summary: list[str] = []
        seen_apps: set[str] = set()
        for item in all_windows:
            process_name = str(item.get("process", "")).strip()
            lowered = process_name.lower()
            if not process_name or lowered == active_app.lower() or lowered in seen_apps:
                continue
            seen_apps.add(lowered)
            other_running_apps_summary.append(process_name.replace(".exe", ""))

        visible_content_summary = detailed_description or current_content or page_summary
        if not visible_content_summary and window_visible_text:
            visible_content_summary = "; ".join(window_visible_text[:4])
        if not visible_content_summary and browser_page_text:
            visible_content_summary = "; ".join(browser_page_text[:3])
        visible_content_summary = ScreenContextCollector._clean_summary_text(visible_content_summary)

        final_user_state_summary = visible_content_summary
        if browser_page_text and not final_user_state_summary:
            final_user_state_summary = "; ".join(browser_page_text[:3])
        final_user_state_summary = ScreenContextCollector._clean_summary_text(final_user_state_summary)
        if active_app and final_user_state_summary:
            final_user_state_summary = f"You're currently using {active_app} and viewing: {final_user_state_summary}"
        elif active_app:
            final_user_state_summary = f"You're currently using {active_app}."

        return {
            "focused_window_summary": focused_window_summary,
            "current_task_summary": current_task_summary,
            "browser_tabs_summary": browser_tabs_summary[:10],
            "browser_address_summary": browser_address_text,
            "browser_page_text_summary": browser_page_text[:8],
            "window_visible_text_summary": window_visible_text[:10],
            "visible_content_summary": visible_content_summary,
            "other_running_apps_summary": other_running_apps_summary[:8],
            "final_user_state_summary": final_user_state_summary,
        }

    async def _synthesize_rich_report(self, context: dict) -> dict:
        facts = {
            "active_app": context.get("active_app", ""),
            "window_title": context.get("window_title", ""),
            "screen_state": context.get("screen_state", ""),
            "page_summary": context.get("page_summary", ""),
            "current_content": context.get("current_content", ""),
            "detailed_description": context.get("detailed_description", ""),
            "visible_content_summary": context.get("visible_content_summary", ""),
            "browser_address_text": context.get("browser_address_text", ""),
            "browser_page_text": context.get("browser_page_text", [])[:8],
            "window_visible_text": context.get("window_visible_text", [])[:10],
            "browser_tabs": [
                str(tab.get("title", "")).strip()
                for tab in context.get("browser_tabs", [])
                if str(tab.get("title", "")).strip()
            ][:12],
            "other_running_apps": context.get("other_running_apps_summary", [])[:8],
            "visible_text": context.get("visible_text", [])[:6],
            "uia_focused_element": context.get("uia_focused_element", ""),
        }
        prompt = RICH_REPORT_PROMPT.format(facts_json=json.dumps(facts, ensure_ascii=False))
        response_text = await self._vlm.generate_text(
            prompt,
            num_predict=256,
            timeout_seconds=60.0,
            num_ctx=1024,
        )
        parsed = self._parse_structured_report(response_text)
        if parsed["focused_window_summary"]:
            return parsed
        return {}

    @staticmethod
    def _parse_structured_report(response_text: str) -> dict:
        parsed: dict[str, str] = {}
        current_key = ""
        for line in response_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                current_key = key.strip().upper()
                parsed[current_key] = value.strip()
                continue
            if current_key:
                parsed[current_key] = f"{parsed[current_key]} {stripped}".strip()

        browser_tabs = [
            item.strip()
            for item in parsed.get("BROWSER_TABS", "").split("|")
            if item.strip()
        ]
        other_apps = [
            item.strip()
            for item in parsed.get("OTHER_RUNNING_APPS", "").split("|")
            if item.strip()
        ]
        return {
            "focused_window_summary": ScreenContextCollector._clean_summary_text(parsed.get("FOCUSED_WINDOW", "")),
            "current_task_summary": ScreenContextCollector._clean_summary_text(parsed.get("CURRENT_VIEW", "")),
            "visible_content_summary": ScreenContextCollector._clean_summary_text(parsed.get("VISIBLE_CONTENT", "")),
            "detailed_description": ScreenContextCollector._clean_summary_text(parsed.get("VISIBLE_CONTENT", "")),
            "browser_tabs_summary": browser_tabs[:10],
            "other_running_apps_summary": other_apps[:8],
            "final_user_state_summary": ScreenContextCollector._clean_summary_text(parsed.get("FINAL_STATE", "")),
        }

    @staticmethod
    def _clean_summary_text(text: str) -> str:
        cleaned = text.strip()
        prefixes = (
            "the user is currently viewing ",
            "the user is viewing ",
            "currently viewing ",
            "the screen shows ",
            "short user-facing summary.",
            "short user-facing summary:",
            "concise but information-dense paragraph describing what is visible on screen.",
            "concise but information-dense paragraph describing what is visible on screen:",
        )
        lowered = cleaned.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        if cleaned:
            return cleaned[0].upper() + cleaned[1:]
        return cleaned


async def capture_screenshot() -> tuple[bytes, tuple[int, int]]:
    collector = ScreenContextCollector(
        vlm=VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
    )
    return await collector.capture_screenshot()


async def get_vlm_context(image_bytes: bytes) -> dict:
    collector = ScreenContextCollector(
        vlm=VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
    )
    return await collector.get_vlm_context(image_bytes)


def get_uia_context() -> dict:
    collector = ScreenContextCollector(
        vlm=VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
    )
    return collector.get_uia_context()


def get_win32_context() -> dict:
    collector = ScreenContextCollector(
        vlm=VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
    )
    return collector.get_win32_context()


async def get_unified_screen_context() -> dict:
    collector = ScreenContextCollector(
        vlm=VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
    )
    return await collector.get_unified_screen_context()
