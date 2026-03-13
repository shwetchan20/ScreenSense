from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class RecordSink(Protocol):
    def write(self, record: dict[str, Any]) -> None:
        ...


class NoopSink:
    def write(self, record: dict[str, Any]) -> None:
        _ = record


class JsonlSink:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")


class FirestoreSink:
    def __init__(self, project_id: str, database: str, collection: str) -> None:
        from google.cloud import firestore  # type: ignore

        kwargs: dict[str, str] = {}
        if project_id:
            kwargs["project"] = project_id
        if database:
            kwargs["database"] = database
        self._client = firestore.Client(**kwargs)
        self._collection = self._client.collection(collection)

    def write(self, record: dict[str, Any]) -> None:
        self._collection.add(record)


class CompositeSink:
    def __init__(self, sinks: list[RecordSink]) -> None:
        self._sinks = sinks

    def write(self, record: dict[str, Any]) -> None:
        for sink in self._sinks:
            try:
                sink.write(record)
            except Exception:
                continue


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

