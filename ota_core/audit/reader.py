"""Audit event read-side seam.

The audit sinks are write-only (`emit` → JSONL). The dashboard (Phase 4C.6)
and `/why` lookup (Phase 4C.7) read from the same JSONL files. This module
adds a thin reader that streams events in timestamp order with optional
filters.

The reader is intentionally separate from the sink protocol so the
in-memory `NullAuditSink` doesn't have to grow a query API and so future
backends (SIEM-shipping in Enterprise edition) can ship their own reader
without touching the write path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ota_core.contracts.audit_event import AuditEvent


@dataclass(frozen=True)
class AuditFilter:
    """Optional filters applied during a read.

    All filters are AND'd. `q` matches a substring against the serialized
    payload (case-insensitive) so the dashboard can offer a text search.
    `event_types` restricts to a set of event_type literals; empty set means
    no restriction.
    """

    start: datetime | None = None
    end: datetime | None = None
    event_types: frozenset[str] = frozenset()
    routine_run_id: str | None = None
    trace_id: str | None = None
    q: str | None = None
    severity_at_least: str | None = None

    def matches(self, event: AuditEvent) -> bool:
        if self.start is not None and event.timestamp < self.start:
            return False
        if self.end is not None and event.timestamp > self.end:
            return False
        if self.event_types and event.event_type not in self.event_types:
            return False
        if self.routine_run_id is not None and event.routine_run_id != self.routine_run_id:
            return False
        if self.trace_id is not None and event.trace_id != self.trace_id:
            return False
        if self.severity_at_least is not None and _severity_rank(event.severity) < _severity_rank(
            self.severity_at_least
        ):
            return False
        if self.q is not None:
            blob = json.dumps(event.model_dump(mode="json"), default=str)
            if self.q.lower() not in blob.lower():
                return False
        return True


_SEVERITY_ORDER = {"debug": 0, "info": 1, "warn": 2, "error": 3, "critical": 4}


def _severity_rank(severity: str) -> int:
    return _SEVERITY_ORDER.get(severity, 0)


@runtime_checkable
class AuditReader(Protocol):
    def scan(self, filter_: AuditFilter | None = None) -> Iterator[AuditEvent]: ...

    def by_trace(self, trace_id: str) -> list[AuditEvent]: ...

    def by_routine_run(self, routine_run_id: str) -> list[AuditEvent]: ...


_MONTHLY_FILE_RE = re.compile(r"^(\d{4})-(\d{2})\.jsonl$")


class FileAuditReader:
    """Reads JSONL events from the directory `FileAuditSink` writes to.

    The reader scans files in chronological order (oldest first), skips
    unrelated names, and parses each line into an `AuditEvent`. Malformed
    lines are skipped silently — the writer is the authority on shape, and
    a partial line during rotation should not crash a query. (A debug log
    line is emitted via `structlog` if logging is wired; v0.1 just drops it.)
    """

    def __init__(self, directory: Path | str) -> None:
        self._directory = Path(directory).expanduser()

    @property
    def directory(self) -> Path:
        return self._directory

    def _monthly_files(self) -> list[Path]:
        if not self._directory.exists():
            return []
        files: list[tuple[tuple[int, int], Path]] = []
        for p in self._directory.iterdir():
            m = _MONTHLY_FILE_RE.match(p.name)
            if m is None:
                continue
            files.append(((int(m.group(1)), int(m.group(2))), p))
        return [p for _, p in sorted(files, key=lambda x: x[0])]

    def _files_in_range(self, start: datetime | None, end: datetime | None) -> Iterable[Path]:
        for p in self._monthly_files():
            m = _MONTHLY_FILE_RE.match(p.name)
            if m is None:
                continue
            year, month = int(m.group(1)), int(m.group(2))
            if start is not None and (year, month) < (start.year, start.month):
                continue
            if end is not None and (year, month) > (end.year, end.month):
                continue
            yield p

    def scan(self, filter_: AuditFilter | None = None) -> Iterator[AuditEvent]:
        f = filter_ or AuditFilter()
        for path in self._files_in_range(f.start, f.end):
            yield from self._scan_file(path, f)

    def _scan_file(self, path: Path, f: AuditFilter) -> Iterator[AuditEvent]:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw: dict[str, Any] = json.loads(line)
                    event = AuditEvent.model_validate(raw)
                except (ValueError, KeyError):
                    continue
                if f.matches(event):
                    yield event

    def by_trace(self, trace_id: str) -> list[AuditEvent]:
        return list(self.scan(AuditFilter(trace_id=trace_id)))

    def by_routine_run(self, routine_run_id: str) -> list[AuditEvent]:
        return list(self.scan(AuditFilter(routine_run_id=routine_run_id)))

    def count(self, filter_: AuditFilter | None = None) -> int:
        return sum(1 for _ in self.scan(filter_))


def utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC) if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
