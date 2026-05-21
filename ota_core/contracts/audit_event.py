from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ota_core.contracts.shared import (
    AwareDatetime,
    DeploymentMode,
    Edition,
    SemVer,
    Severity,
)

PrincipalType = Literal["operator", "system", "user", "service"]

EventType = Literal[
    "auth.login",
    "auth.logout",
    "auth.failed",
    "auth.mfa_challenge",
    "auth.mfa_succeeded",
    "auth.mfa_failed",
    "secret.read",
    "secret.rotated",
    "secret.write_attempt",
    "secret.not_found",
    "routine.loaded",
    "routine.load_failed",
    "routine.updated",
    "routine.rejected",
    "routine.run_started",
    "routine.run_completed",
    "routine.run_failed",
    "routine.run_timed_out",
    "routine.run_killed",
    "routine.run_terminated_incomplete",
    "gate.proposed",
    "gate.approved",
    "gate.rejected",
    "gate.modified_and_approved",
    "gate.auto_approved_by_similarity",
    "gate.expired",
    "tool_call.invoked",
    "tool_call.succeeded",
    "tool_call.failed",
    "tool_call.blocked_by_policy",
    "tool_call.budget_exceeded",
    "llm.request",
    "llm.response",
    "llm.error",
    "llm.rate_limited",
    "llm.budget_exceeded",
    "integration.connected",
    "integration.disconnected",
    "integration.auth_refreshed",
    "integration.auth_failed",
    "integration.call_failed",
    "integration.load_skipped",
    "integration.messaging.action_triggered",
    "integration.email.bounce_received",
    "integration.email.reply_received",
    "integration.email.delivery_confirmed",
    "integration.email.auto_response_received",
    "integration.gmail.message_received",
    "routine_source.fetched",
    "routine_source.signature_verified",
    "routine_source.signature_failed",
    "routine_source.update_applied",
    "routine_source.update_deferred",
    "routine_source.routine_killed",
    "policy.violation",
    "policy.egress_blocked",
    "policy.pii_leak_attempt",
    "policy.secret_leak_attempt",
    "policy.kill_override_attempted",
    "policy.credential_revoked",
    "policy.credential_revocation_failed",
    "policy.shared_credential_emergency_exposure",
    "policy.identity_credential_emergency_exposure",
    "policy.scope_escalation_attempt",
    "policy.budget_exceeded",
    "policy.webhook_signature_failed",
    "system.startup",
    "system.shutdown",
    "system.config_reloaded",
    "system.health_check_failed",
    "system.crash_loop_detected",
    "system.kill_lock_cleared",
    "system.notification_storm_summary",
    "data_subject.access_requested",
    "data_subject.erasure_requested",
    "data_subject.erasure_completed",
    "artifact.emitted",
    "artifact.claimed",
    "artifact.completed",
    "artifact.failed",
    "artifact.auto_expired",
]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: PrincipalType
    idp_sub: str | None = None
    display_name: str | None = None


class DeploymentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    mode: DeploymentMode
    edition: Edition
    version: SemVer


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: str = Field(min_length=1)
    version: SemVer


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    event_id: str = Field(min_length=1)
    timestamp: AwareDatetime
    event_type: EventType
    severity: Severity
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    routine_run_id: str | None = None
    request_id: str | None = None
    principal: Principal
    tenant_id: str | None = None
    deployment: DeploymentInfo
    source: SourceInfo
    payload: dict[str, Any] = Field(default_factory=dict)
    redactions_applied: list[str] = Field(default_factory=list)


TerminationCause = Literal[
    "hard_kill_timeout",
    "emergency_kill",
    "framework_restart",
    "routine_crash",
    "budget_exceeded",
    "gate_timeout_after_kill",
]


class GatePendingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str
    auto_rejected: bool
    reason: str | None = None


class ArtifactEmittedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["pending", "claimed", "completed", "failed", "expired", "auto_expired"]
    stale_artifact_ttl: str
    expires_at: AwareDatetime
    consumers: list[str] = Field(default_factory=list)


class IntegrationCallCompletedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: str
    operation: str
    count: int = Field(default=1, ge=0)
    result: Literal["succeeded", "failed", "partial"] = "succeeded"
    note: str | None = None


class IntegrationCallAbortedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: str
    operation: str
    state: Literal["never_invoked", "aborted_mid_flight"]


class RoutineRunTerminatedIncompletePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: TerminationCause
    routine_id: str
    routine_version: SemVer
    run_started_at: AwareDatetime
    run_terminated_at: AwareDatetime
    steps_completed: list[str] = Field(default_factory=list)
    steps_in_flight: list[str] = Field(default_factory=list)
    steps_never_started: list[str] = Field(default_factory=list)
    gates_pending: list[GatePendingEntry] = Field(default_factory=list)
    artifacts_emitted: list[ArtifactEmittedEntry] = Field(default_factory=list)
    integration_calls_completed_during_termination: list[IntegrationCallCompletedEntry] = Field(
        default_factory=list
    )
    integration_calls_aborted: list[IntegrationCallAbortedEntry] = Field(default_factory=list)
    cleanup_recommendations: list[str] = Field(default_factory=list)
