from __future__ import annotations

from typing import Any

from screensense.models import ScreenObservation
from screensense.storage.sinks import CompositeSink, FirestoreSink, JsonlSink, NoopSink, RecordSink, utc_now_iso


class ObservationPersister:
    def __init__(
        self,
        sink_mode: str,
        local_path: str,
        firestore_project_id: str,
        firestore_database: str,
        firestore_collection: str,
    ) -> None:
        self._sink = self._build_sink(
            sink_mode=sink_mode,
            local_path=local_path,
            firestore_project_id=firestore_project_id,
            firestore_database=firestore_database,
            firestore_collection=firestore_collection,
        )

    def persist(self, item: ScreenObservation) -> None:
        record: dict[str, Any] = {
            "ts": utc_now_iso(),
            "changed_percent": item.changed_percent,
            "decision": item.decision.model_dump(),
        }
        self._sink.write(record)

    @staticmethod
    def _build_sink(
        *,
        sink_mode: str,
        local_path: str,
        firestore_project_id: str,
        firestore_database: str,
        firestore_collection: str,
    ) -> RecordSink:
        local_sink = JsonlSink(local_path)
        if sink_mode == "none":
            return NoopSink()
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
