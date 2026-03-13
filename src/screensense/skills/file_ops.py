from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Callable


class FileOps:
    def __init__(self, approval_callback: Callable[[str, str], bool] | None = None) -> None:
        self._approval_callback = approval_callback

    def read_file(self, path: str) -> str:
        file_path = Path(path)
        return file_path.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> bool:
        if self._approval_callback is None:
            return False
        if not self._approval_callback(path, "write_file"):
            return False
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def create_file(self, path: str, content: str) -> bool:
        try:
            file_path = Path(path)
            if file_path.exists():
                return False
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def list_directory(self, path: str) -> list[str]:
        dir_path = Path(path)
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        return sorted(str(entry) for entry in dir_path.iterdir())

    def find_files(self, pattern: str, root: str) -> list[str]:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            return []
        matches: list[str] = []
        for entry in root_path.rglob("*"):
            if entry.is_file() and fnmatch.fnmatch(entry.name, pattern):
                matches.append(str(entry))
        return sorted(matches)
