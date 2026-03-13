from pathlib import Path

from screensense.core.audit_logger import AuditLogger


def test_audit_logger_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(enabled=True, path=str(path))
    logger.log("interrupt_evaluated", {"allow_interrupt": False, "reason": "low_confidence"})
    content = path.read_text(encoding="utf-8")
    assert "interrupt_evaluated" in content
    assert "low_confidence" in content

