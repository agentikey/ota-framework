from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ota_core.audit import AuditFilter, FileAuditReader, FileAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def _write_events(directory: Path, count: int = 3) -> FileAuditSink:
    sink = FileAuditSink(directory, deployment=_deployment(), source=_source())
    for i in range(count):
        sink.emit(
            event_type="tool_call.invoked",
            severity="info",
            principal=_principal(),
            payload={"verb": f"v{i}"},
            trace_id=f"{i:032x}",
            routine_run_id=f"rr-{i}",
        )
    sink.close()
    return sink


def test_scan_returns_all_events(tmp_path: Path) -> None:
    _write_events(tmp_path, count=5)
    reader = FileAuditReader(tmp_path)
    events = list(reader.scan())
    assert len(events) == 5


def test_scan_filters_by_event_type(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(event_type="tool_call.invoked", severity="info", principal=_principal())
    sink.emit(event_type="gate.proposed", severity="info", principal=_principal())
    sink.emit(event_type="tool_call.succeeded", severity="info", principal=_principal())
    sink.close()
    reader = FileAuditReader(tmp_path)
    events = list(reader.scan(AuditFilter(event_types=frozenset({"gate.proposed"}))))
    assert len(events) == 1
    assert events[0].event_type == "gate.proposed"


def test_by_trace_returns_only_matching(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        trace_id="a" * 32,
    )
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        trace_id="b" * 32,
    )
    sink.close()
    events = FileAuditReader(tmp_path).by_trace("a" * 32)
    assert len(events) == 1


def test_by_routine_run_returns_only_matching(tmp_path: Path) -> None:
    _write_events(tmp_path, count=3)
    events = FileAuditReader(tmp_path).by_routine_run("rr-1")
    assert len(events) == 1
    assert events[0].routine_run_id == "rr-1"


def test_q_substring_search(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        payload={"verb": "send_message"},
    )
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        payload={"verb": "list_recent_messages"},
    )
    sink.close()
    reader = FileAuditReader(tmp_path)
    assert len(list(reader.scan(AuditFilter(q="send_message")))) == 1
    assert len(list(reader.scan(AuditFilter(q="list_recent")))) == 1


def test_severity_filter(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(event_type="tool_call.invoked", severity="debug", principal=_principal())
    sink.emit(event_type="tool_call.invoked", severity="info", principal=_principal())
    sink.emit(event_type="tool_call.invoked", severity="warn", principal=_principal())
    sink.emit(event_type="tool_call.invoked", severity="error", principal=_principal())
    sink.close()
    reader = FileAuditReader(tmp_path)
    assert len(list(reader.scan(AuditFilter(severity_at_least="warn")))) == 2


def test_count_helper(tmp_path: Path) -> None:
    _write_events(tmp_path, count=7)
    assert FileAuditReader(tmp_path).count() == 7


def test_missing_directory_returns_no_events(tmp_path: Path) -> None:
    reader = FileAuditReader(tmp_path / "does_not_exist")
    assert list(reader.scan()) == []


def test_skips_garbage_lines(tmp_path: Path) -> None:
    _write_events(tmp_path, count=2)
    file = next(tmp_path.glob("*.jsonl"))
    with file.open("a", encoding="utf-8") as fh:
        fh.write("\nnot json at all\n")
        fh.write("\n")  # blank
    reader = FileAuditReader(tmp_path)
    assert reader.count() == 2


def test_start_end_filters_by_month(tmp_path: Path) -> None:
    """Files outside [start_month, end_month] are skipped."""
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        timestamp=datetime(2026, 1, 15, tzinfo=UTC),
    )
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        timestamp=datetime(2026, 5, 15, tzinfo=UTC),
    )
    sink.close()
    reader = FileAuditReader(tmp_path)
    events = list(
        reader.scan(
            AuditFilter(
                start=datetime(2026, 4, 1, tzinfo=UTC),
                end=datetime(2026, 6, 30, tzinfo=UTC),
            )
        )
    )
    assert len(events) == 1
    assert events[0].timestamp.month == 5
