from pathlib import Path

from screensense.memory.persistence import ObservationPersister
from screensense.memory.store import RollingMemory
from screensense.models import ScreenObservation, VisionDecision


def test_memory_persister_writes_local_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "memory.jsonl"
    persister = ObservationPersister(
        sink_mode="local",
        local_path=str(path),
        firestore_project_id="",
        firestore_database="(default)",
        firestore_collection="screensense_memory",
    )
    mem = RollingMemory(max_items=10, writer=persister)
    mem.add(
        ScreenObservation(
            changed_percent=42.0,
            decision=VisionDecision(context="VS Code", should_interrupt=False),
        )
    )
    content = path.read_text(encoding="utf-8")
    assert "changed_percent" in content
    assert "VS Code" in content

