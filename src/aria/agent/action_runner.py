import os
from pathlib import Path


class ActionRunner:
    def __init__(self, sandbox_workspace: str | None = None) -> None:
        raw_root = sandbox_workspace or os.environ.get("ARIA_SANDBOX_WORKSPACE", "research/test_workspace")
        self._workspace = Path(raw_root).resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)

    def _validate_sandbox_path(self, raw_path: str) -> Path:
        p = Path(raw_path)
        if not p.is_absolute():
            candidate = (self._workspace / p).resolve()
        else:
            candidate = p.resolve()
        try:
            candidate.relative_to(self._workspace)
        except ValueError as exc:
            raise PermissionError(f"Action attempted path outside sandbox workspace: {candidate}") from exc
        return candidate

    def run(self, action_spec: dict) -> None:
        action = str(action_spec.get("action", "")).lower()

        if action in {"write_file", "create_file"}:
            path = action_spec.get("path") or action_spec.get("target") or action_spec.get("file")
            content = action_spec.get("content") or action_spec.get("text", "")
            if not path:
                raise ValueError("Missing destination path for write_file")
            safe_path = self._validate_sandbox_path(str(path))
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(str(content), encoding="utf-8")
            return

        if action in {"create_dir", "mkdir"}:
            path = action_spec.get("path") or action_spec.get("target") or action_spec.get("directory")
            if not path:
                raise ValueError("Missing path for create_dir")
            safe_path = self._validate_sandbox_path(str(path))
            safe_path.mkdir(parents=True, exist_ok=True)
            return

        if action == "click":
            if action_spec.get("element_id_missing"):
                raise ValueError("Element ID not found in screen context")
            coords = action_spec.get("coords")
            if not isinstance(coords, dict):
                raise ValueError("Click action requires coordinates or valid element_id")
            if os.environ.get("ARIA_SANDBOX_MODE", "1").strip().lower() in {"1", "true"}:
                return
            import pyautogui

            pyautogui.click(int(coords["x"]), int(coords["y"]))
            return

        if action == "type":
            text = str(action_spec.get("text", ""))
            if os.environ.get("ARIA_SANDBOX_MODE", "1").strip().lower() in {"1", "true"}:
                return
            import pyautogui

            pyautogui.typewrite(text, interval=0.05)
            return

        if action == "key":
            key = action_spec.get("key", "")
            if os.environ.get("ARIA_SANDBOX_MODE", "1").strip().lower() in {"1", "true"}:
                return
            import pyautogui

            if isinstance(key, list):
                pyautogui.hotkey(*[str(k) for k in key])
            else:
                pyautogui.hotkey(str(key))
            return

        if action == "scroll":
            amount = int(action_spec.get("amount", 0))
            if os.environ.get("ARIA_SANDBOX_MODE", "1").strip().lower() in {"1", "true"}:
                return
            import pyautogui

            coords = action_spec.get("coords")
            if isinstance(coords, dict):
                pyautogui.scroll(amount, x=int(coords["x"]), y=int(coords["y"]))
            else:
                pyautogui.scroll(amount)
            return

        raise ValueError(f"Unsupported action: {action}")

