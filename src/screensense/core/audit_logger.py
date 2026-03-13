from __future__ import annotations

from typing import Any

from screensense.storage.sinks import CompositeSink, FirestoreSink, JsonlSink, NoopSink, RecordSink, utc_now_iso


class AuditLogger:
    def __init__(
        self,
        enabled: bool,
        path: str,
        sink_mode: str = "local",
        firestore_project_id: str = "",
        firestore_database: str = "(default)",
        firestore_collection: str = "screensense_audit",
    ) -> None:
        self._enabled = enabled
        self._sink = self._build_sink(
            enabled=enabled,
            path=path,
            sink_mode=sink_mode,
            firestore_project_id=firestore_project_id,
            firestore_database=firestore_database,
            firestore_collection=firestore_collection,
        )

    def log(self, event: str, payload: dict[str, Any]) -> None:
        if not self._enabled:
            return
        record = {
            "ts": utc_now_iso(),
            "event": event,
            **payload,
        }
        self._sink.write(record)

    @staticmethod
    def _build_sink(
        *,
        enabled: bool,
        path: str,
        sink_mode: str,
        firestore_project_id: str,
        firestore_database: str,
        firestore_collection: str,
    ) -> RecordSink:
        if not enabled or sink_mode == "none":
            return NoopSink()
        local_sink = JsonlSink(path)
        if sink_mode == "local":
            return local_sink
        if sink_mode == "firestore":
            try:
                return FirestoreSink(
                    project_id=firestore_project_id,
                    database=firestore_database,
                    collection=firestore_collection,
                )
            except Exception:
                return local_sink
        if sink_mode == "dual":
            try:
                firestore_sink = FirestoreSink(
                    project_id=firestore_project_id,
                    database=firestore_database,
                    collection=firestore_collection,
                )
                return CompositeSink([local_sink, firestore_sink])
            except Exception:
                return local_sink
        return local_sink
