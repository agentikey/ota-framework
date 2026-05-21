"""Audit log viewer endpoints — filterable, searchable, CSV-exportable."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ota_core.audit.reader import AuditFilter
from ota_dashboard_api.app import DashboardState, dashboard_state
from ota_dashboard_api.models import AuditEventResponse, AuditScanResponse

router = APIRouter()


def _to_response(event: Any) -> AuditEventResponse:
    return AuditEventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        severity=event.severity,
        timestamp=event.timestamp,
        trace_id=event.trace_id,
        routine_run_id=event.routine_run_id,
        payload=event.payload,
        principal_id=event.principal.id,
        principal_type=event.principal.type,
    )


def _filter(
    *,
    start: datetime | None,
    end: datetime | None,
    event_types: list[str] | None,
    routine_run_id: str | None,
    trace_id: str | None,
    q: str | None,
    severity_at_least: str | None,
) -> AuditFilter:
    return AuditFilter(
        start=start,
        end=end,
        event_types=frozenset(event_types or ()),
        routine_run_id=routine_run_id,
        trace_id=trace_id,
        q=q,
        severity_at_least=severity_at_least,
    )


@router.get("/audit", response_model=AuditScanResponse)
def scan_audit(
    start: datetime | None = None,
    end: datetime | None = None,
    event_type: list[str] | None = Query(default=None),
    routine_run_id: str | None = None,
    trace_id: str | None = None,
    q: str | None = None,
    severity_at_least: str | None = None,
    limit: int = 200,
    state: DashboardState = Depends(dashboard_state),
) -> AuditScanResponse:
    filter_ = _filter(
        start=start,
        end=end,
        event_types=event_type,
        routine_run_id=routine_run_id,
        trace_id=trace_id,
        q=q,
        severity_at_least=severity_at_least,
    )
    events: list[AuditEventResponse] = []
    for ev in state.audit_reader.scan(filter_):
        events.append(_to_response(ev))
        if len(events) >= limit:
            break
    return AuditScanResponse(events=events, next_cursor=None)


@router.get("/audit/trace/{trace_id}", response_model=AuditScanResponse)
def by_trace(
    trace_id: str,
    state: DashboardState = Depends(dashboard_state),
) -> AuditScanResponse:
    events = [_to_response(e) for e in state.audit_reader.by_trace(trace_id)]
    return AuditScanResponse(events=events, next_cursor=None)


@router.get("/audit/run/{routine_run_id}", response_model=AuditScanResponse)
def by_run(
    routine_run_id: str,
    state: DashboardState = Depends(dashboard_state),
) -> AuditScanResponse:
    events = [_to_response(e) for e in state.audit_reader.by_routine_run(routine_run_id)]
    return AuditScanResponse(events=events, next_cursor=None)


@router.get("/audit.csv", response_class=Response)
def export_csv(
    start: datetime | None = None,
    end: datetime | None = None,
    event_type: list[str] | None = Query(default=None),
    routine_run_id: str | None = None,
    trace_id: str | None = None,
    q: str | None = None,
    severity_at_least: str | None = None,
    state: DashboardState = Depends(dashboard_state),
) -> Response:
    filter_ = _filter(
        start=start,
        end=end,
        event_types=event_type,
        routine_run_id=routine_run_id,
        trace_id=trace_id,
        q=q,
        severity_at_least=severity_at_least,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["timestamp", "event_type", "severity", "trace_id", "routine_run_id", "principal_id"]
    )
    for ev in state.audit_reader.scan(filter_):
        writer.writerow(
            [
                ev.timestamp.isoformat(),
                ev.event_type,
                ev.severity,
                ev.trace_id or "",
                ev.routine_run_id or "",
                ev.principal.id,
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ota_audit.csv"'},
    )
