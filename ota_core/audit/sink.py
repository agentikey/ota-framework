from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Protocol, runtime_checkable

from ota_core.audit.errors import AuditSinkError
from ota_core.audit.ids import new_event_id
from ota_core.contracts.audit_event import (
    AuditEvent,
    DeploymentInfo,
    EventType,
    Principal,
    SourceInfo,
)
from ota_core.contracts.shared import SemVer, Severity
from ota_core.trace import current_trace_id, new_trace_id


@runtime_checkable
class AuditSink(Protocol):
    def emit(
        self,
        *,
        event_type: EventType,
        severity: Severity,
        principal: Principal,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        routine_run_id: str | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
        redactions_applied: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent: ...

    def close(self) -> None: ...


def _default_clock() -> datetime:
    return datetime.now(UTC)


class FileAuditSink:
    def __init__(
        self,
        directory: Path | str,
        *,
        deployment: DeploymentInfo,
        source: SourceInfo,
        schema_version: SemVer = "1.0.0",
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._directory = Path(directory).expanduser()
        self._directory.mkdir(parents=True, exist_ok=True)
        self._deployment = deployment
        self._source = source
        self._schema_version = schema_version
        self._clock = clock
        self._file: IO[str] | None = None
        self._current_month: tuple[int, int] | None = None
        self._lock = threading.Lock()

    def emit(
        self,
        *,
        event_type: EventType,
        severity: Severity,
        principal: Principal,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        routine_run_id: str | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
        redactions_applied: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        when = timestamp if timestamp is not None else self._clock()
        resolved_trace = trace_id if trace_id is not None else current_trace_id()
        if resolved_trace is None:
            resolved_trace = new_trace_id()
        event = AuditEvent(
            schema_version=self._schema_version,
            event_id=new_event_id(),
            timestamp=when,
            event_type=event_type,
            severity=severity,
            trace_id=resolved_trace,
            routine_run_id=routine_run_id,
            request_id=request_id,
            principal=principal,
            tenant_id=tenant_id,
            deployment=self._deployment,
            source=self._source,
            payload=payload or {},
            redactions_applied=redactions_applied or [],
        )
        self._write(event)
        return event

    def _write(self, event: AuditEvent) -> None:
        with self._lock:
            self._rotate_if_needed(event.timestamp)
            assert self._file is not None
            try:
                self._file.write(event.model_dump_json(exclude_none=False) + "\n")
                self._file.flush()
            except OSError as e:
                raise AuditSinkError(f"failed to write audit event {event.event_id}: {e}") from e

    def _rotate_if_needed(self, ts: datetime) -> None:
        ts_utc = ts.astimezone(UTC)
        key = (ts_utc.year, ts_utc.month)
        if self._file is not None and self._current_month == key:
            return
        if self._file is not None:
            self._file.close()
            self._file = None
        path = self._directory / f"{ts_utc.year:04d}-{ts_utc.month:02d}.jsonl"
        try:
            self._file = path.open("a", encoding="utf-8", newline="\n")
        except OSError as e:
            raise AuditSinkError(f"failed to open audit file {path}: {e}") from e
        self._current_month = key

    def current_path(self) -> Path | None:
        if self._current_month is None:
            return None
        year, month = self._current_month
        return self._directory / f"{year:04d}-{month:02d}.jsonl"

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
                self._current_month = None

    def __enter__(self) -> FileAuditSink:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class NullAuditSink:
    def __init__(
        self,
        *,
        deployment: DeploymentInfo,
        source: SourceInfo,
        schema_version: SemVer = "1.0.0",
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._deployment = deployment
        self._source = source
        self._schema_version = schema_version
        self._clock = clock
        self.events: list[AuditEvent] = []

    def emit(
        self,
        *,
        event_type: EventType,
        severity: Severity,
        principal: Principal,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        routine_run_id: str | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
        redactions_applied: list[str] | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        when = timestamp if timestamp is not None else self._clock()
        resolved_trace = trace_id if trace_id is not None else current_trace_id()
        if resolved_trace is None:
            resolved_trace = new_trace_id()
        event = AuditEvent(
            schema_version=self._schema_version,
            event_id=new_event_id(),
            timestamp=when,
            event_type=event_type,
            severity=severity,
            trace_id=resolved_trace,
            routine_run_id=routine_run_id,
            request_id=request_id,
            principal=principal,
            tenant_id=tenant_id,
            deployment=self._deployment,
            source=self._source,
            payload=payload or {},
            redactions_applied=redactions_applied or [],
        )
        self.events.append(event)
        return event

    def close(self) -> None:
        return None
