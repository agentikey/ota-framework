from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Literal, Protocol, runtime_checkable

from ota_core.trace import current_span_id, current_trace_id, new_span_id

MetricKind = Literal["counter", "gauge", "histogram"]


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    started_at: datetime
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    ended_at: datetime | None = None
    status: Literal["ok", "error"] = "ok"

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "name": name,
                "timestamp": _utc_now().isoformat(),
                "attributes": attributes or {},
            }
        )


@runtime_checkable
class ObservabilitySink(Protocol):
    def metric(
        self,
        name: str,
        value: float,
        *,
        kind: MetricKind = "counter",
        attributes: dict[str, str] | None = None,
    ) -> None: ...

    def span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Any: ...

    def close(self) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _Writer(Protocol):
    def write(self, payload: dict[str, Any]) -> None: ...


class _LineWriter:
    def __init__(self, stream: IO[str], lock: threading.Lock) -> None:
        self._stream = stream
        self._lock = lock

    def write(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":"), default=str) + "\n"
        with self._lock:
            self._stream.write(line)
            self._stream.flush()


class _BaseObservabilitySink:
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._writer: _Writer | None = None

    def _emit(self, payload: dict[str, Any]) -> None:
        if self._writer is not None:
            self._writer.write(payload)

    def metric(
        self,
        name: str,
        value: float,
        *,
        kind: MetricKind = "counter",
        attributes: dict[str, str] | None = None,
    ) -> None:
        self._emit(
            {
                "kind": "metric",
                "type": kind,
                "name": name,
                "value": value,
                "trace_id": current_trace_id(),
                "span_id": current_span_id(),
                "timestamp": self._clock().isoformat(),
                "attributes": attributes or {},
            }
        )

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Span]:
        trace_id = current_trace_id() or new_span_id() + new_span_id()
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=new_span_id(),
            parent_span_id=current_span_id(),
            started_at=self._clock(),
            attributes=dict(attributes or {}),
        )
        try:
            yield span
        except BaseException:
            span.status = "error"
            raise
        finally:
            span.ended_at = self._clock()
            self._emit(
                {
                    "kind": "span",
                    "name": span.name,
                    "trace_id": span.trace_id,
                    "span_id": span.span_id,
                    "parent_span_id": span.parent_span_id,
                    "started_at": span.started_at.isoformat(),
                    "ended_at": span.ended_at.isoformat(),
                    "duration_ms": (span.ended_at - span.started_at).total_seconds() * 1000.0,
                    "status": span.status,
                    "attributes": span.attributes,
                    "events": span.events,
                }
            )

    def close(self) -> None:
        return None


class FileObservabilitySink(_BaseObservabilitySink):
    def __init__(
        self,
        path: Path | str,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        super().__init__(clock=clock)
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file: IO[str] = self._path.open("a", encoding="utf-8", newline="\n")
        self._writer = _LineWriter(self._file, self._lock)

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            if self._writer is not None:
                self._file.close()
                self._writer = None

    def __enter__(self) -> FileObservabilitySink:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class StdoutObservabilitySink(_BaseObservabilitySink):
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        super().__init__(clock=clock)
        self._writer = _LineWriter(sys.stdout, self._lock)


class NullObservabilitySink(_BaseObservabilitySink):
    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        super().__init__(clock=clock)
        self.records: list[dict[str, Any]] = []
        self._writer = _RecordingWriter(self.records, self._lock)


class _RecordingWriter:
    def __init__(self, records: list[dict[str, Any]], lock: threading.Lock) -> None:
        self._records = records
        self._lock = lock

    def write(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._records.append(payload)
