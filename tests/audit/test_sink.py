from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ota_core.audit import AuditSink, FileAuditSink, NullAuditSink, new_event_id
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.trace import TRACE_ID_PATTERN, bind_trace


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="test-deploy", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="audit-test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test Operator")


def test_new_event_id_is_uuid_v7_shaped() -> None:
    for _ in range(50):
        eid = new_event_id()
        assert len(eid) == 36
        assert eid.count("-") == 4
        assert eid[14] == "7", f"version nibble must be 7, got {eid!r}"
        assert eid[19] in {"8", "9", "a", "b"}, f"variant nibble must be 10xx, got {eid!r}"


def test_new_event_id_monotonic_within_millisecond() -> None:
    ids = sorted(new_event_id() for _ in range(20))
    assert ids == sorted(ids)


def test_file_sink_emits_jsonl_event(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    event = sink.emit(
        event_type="system.startup",
        severity="info",
        principal=_principal(),
        payload={"hello": "world"},
    )
    sink.close()

    ts_utc = event.timestamp.astimezone(UTC)
    path = tmp_path / f"{ts_utc.year:04d}-{ts_utc.month:02d}.jsonl"
    assert path.exists()

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["event_id"] == event.event_id
    assert payload["event_type"] == "system.startup"
    assert payload["severity"] == "info"
    assert payload["payload"] == {"hello": "world"}
    assert TRACE_ID_PATTERN.match(payload["trace_id"])


def test_file_sink_appends_multiple_events(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    for i in range(5):
        sink.emit(
            event_type="tool_call.invoked",
            severity="info",
            principal=_principal(),
            payload={"i": i},
        )
    sink.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    indexes = [json.loads(line)["payload"]["i"] for line in lines]
    assert indexes == [0, 1, 2, 3, 4]


def test_file_sink_rotates_by_month(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(
        event_type="system.startup",
        severity="info",
        principal=_principal(),
        timestamp=datetime(2026, 5, 31, 23, 59, 59, tzinfo=UTC),
    )
    sink.emit(
        event_type="system.shutdown",
        severity="info",
        principal=_principal(),
        timestamp=datetime(2026, 6, 1, 0, 0, 1, tzinfo=UTC),
    )
    sink.close()

    may = tmp_path / "2026-05.jsonl"
    june = tmp_path / "2026-06.jsonl"
    assert may.exists() and june.exists()
    assert "system.startup" in may.read_text()
    assert "system.shutdown" in june.read_text()


def test_file_sink_uses_current_trace_when_unset(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    trace = "abc12300abc12300abc12300abc12300"
    with bind_trace(trace_id=trace):
        event = sink.emit(
            event_type="policy.violation",
            severity="warn",
            principal=_principal(),
        )
    assert event.trace_id == trace
    sink.close()


def test_file_sink_creates_directory_lazily(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "audit"
    sink = FileAuditSink(nested, deployment=_deployment(), source=_source())
    sink.emit(event_type="system.startup", severity="info", principal=_principal())
    sink.close()
    assert nested.is_dir()


def test_file_sink_context_manager_closes(tmp_path: Path) -> None:
    with FileAuditSink(tmp_path, deployment=_deployment(), source=_source()) as sink:
        sink.emit(event_type="system.startup", severity="info", principal=_principal())
    assert sink.current_path() is None


def test_null_sink_records_in_memory() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    event = sink.emit(
        event_type="gate.approved",
        severity="info",
        principal=_principal(),
        payload={"gate_id": "send"},
    )
    assert sink.events == [event]
    sink.close()


def test_protocol_satisfaction() -> None:
    assert isinstance(NullAuditSink(deployment=_deployment(), source=_source()), AuditSink)


def test_file_sink_jsonl_line_format_is_strict(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(event_type="system.startup", severity="info", principal=_principal())
    sink.close()
    path = next(tmp_path.glob("*.jsonl"))
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r" not in raw


def test_file_sink_emit_after_close_reopens(tmp_path: Path) -> None:
    sink = FileAuditSink(tmp_path, deployment=_deployment(), source=_source())
    sink.emit(event_type="system.startup", severity="info", principal=_principal())
    sink.close()
    sink.emit(event_type="system.shutdown", severity="info", principal=_principal())
    sink.close()
    path = next(tmp_path.glob("*.jsonl"))
    assert len(path.read_text().splitlines()) == 2


@pytest.mark.parametrize(
    "mode,edition",
    [("vps", "core"), ("managed", "core"), ("managed", "enterprise")],
)
def test_file_sink_records_deployment_info(tmp_path: Path, mode: str, edition: str) -> None:
    deployment = DeploymentInfo(id="d", mode=mode, edition=edition, version="0.1.0")  # type: ignore[arg-type]
    sink = FileAuditSink(tmp_path, deployment=deployment, source=_source())
    sink.emit(event_type="system.startup", severity="info", principal=_principal())
    sink.close()
    line = next(tmp_path.glob("*.jsonl")).read_text().splitlines()[0]
    parsed = json.loads(line)
    assert parsed["deployment"]["mode"] == mode
    assert parsed["deployment"]["edition"] == edition
