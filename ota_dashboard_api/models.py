"""Pydantic response models for the dashboard API.

Single source of truth for the OpenAPI schema. The frontend imports
TypeScript types generated from these via `@hey-api/openapi-ts`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    version: str


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------


class ApprovalQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    routine_id: str
    routine_run_id: str
    gate_id: str
    status: str
    summary: str
    kind: str | None = None
    payload: dict[str, Any]
    similarity_key: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ApprovalQueueListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ApprovalQueueItem]


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "reject", "edit_and_approve", "remember_and_approve"]
    edits: dict[str, Any] | None = None
    reason: str | None = None


class ApprovalDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: str
    decided_at: datetime


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    event_type: str
    severity: str
    timestamp: datetime
    trace_id: str | None = None
    routine_run_id: str | None = None
    payload: dict[str, Any] | None = None
    principal_id: str
    principal_type: str


class AuditScanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[AuditEventResponse]
    next_cursor: str | None = None


# ---------------------------------------------------------------------------
# /why
# ---------------------------------------------------------------------------


class WhyEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: str
    kind: str
    description: str
    payload: dict[str, Any]


class WhyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_id: str
    entries: list[WhyEntryModel]


# ---------------------------------------------------------------------------
# Knobs
# ---------------------------------------------------------------------------


class KnobValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: str
    value: Any | None = None
    default: Any | None = None
    description: str = ""


class RoutineKnobsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routine_id: str
    knobs: list[KnobValue]


class KnobsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knobs: dict[str, Any] = Field(default_factory=dict)


class KnobsUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    routine_id: str
    applied: dict[str, Any]


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------


class FleetEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deployment_id: str
    edition: str
    framework_version: str
    routines: list[str]


class FleetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[FleetEntry]


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class CriticalBannerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool
    severity: Literal["info", "warn", "error", "critical"] | None = None
    title: str | None = None
    description: str | None = None
    raised_at: datetime | None = None
