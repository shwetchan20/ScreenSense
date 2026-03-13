from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from screensense.core.action_gate import ActionGate


class CodeOps:
    _CMD_ALLOWLIST = {"python", "pytest", "pip", "git", "npm", "node"}

    def __init__(self, action_gate: ActionGate | None = None) -> None:
        self._gate = action_gate

    def read_file(self, path: str) -> str:
        if not self._approve(f"read_file {path}", "low"):
            return ""
        return Path(path).read_text(encoding="utf-8")

    def patch_file(self, path: str, old_text: str, new_text: str) -> bool:
        if not self._approve(f"patch_file {path}", "medium"):
            return False
        file_path = Path(path)
        if not file_path.exists():
            return False
        original = file_path.read_text(encoding="utf-8")
        if old_text not in original:
            return False
        updated = original.replace(old_text, new_text, 1)
        file_path.write_text(updated, encoding="utf-8")
        errors = self.get_syntax_errors(path)
        if errors:
            file_path.write_text(original, encoding="utf-8")
            return False
        return True

    def get_syntax_errors(self, path: str) -> list[str]:
        if not self._approve(f"get_syntax_errors {path}", "low"):
            return ["approval_required"]
        if not path.lower().endswith(".py"):
            return []
        cmd = ["python", "-m", "py_compile", path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return []
        return [line for line in (result.stderr or "").splitlines() if line.strip()]

    def run_command(self, cmd: list[str]) -> str:
        if not cmd:
            return "empty command"
        if cmd[0] not in self._CMD_ALLOWLIST:
            return "blocked command"
        preview = f"run_command {' '.join(cmd)}"
        if not self._approve(preview, "medium"):
            return "approval denied"
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return "timeout"
        output = (result.stdout or "") + (result.stderr or "")
        return output.strip()

    def git_status(self) -> str:
        if not self._approve("git_status", "low"):
            return ""
        result = subprocess.run(["git", "status", "-sb"], capture_output=True, text=True)
        return (result.stdout or "").strip()

    def git_commit(self, message: str) -> bool:
        if not message.strip():
            return False
        if not self._approve(f"git_commit {message}", "medium"):
            return False
        result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        return result.returncode == 0

    def _approve(self, preview: str, risk: str) -> bool:
        if self._gate is None:
            return False
        return self._gate.approve(preview, risk)
