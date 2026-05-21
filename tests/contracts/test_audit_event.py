from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ota_core.contracts import (
    AuditEvent,
    RoutineRunTerminatedIncompletePayload,
)


def test_full_envelope_from_contracts_md() -> None:
    AuditEvent.model_validate(
        {
            "schema_version": "1.0.0",
            "event_id": "01HXXX",
            "timestamp": "2026-05-13T14:32:17.412Z",
            "event_type": "gate.approved",
            "severity": "info",
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
            "routine_run_id": "0192fc83-7bb2-7c5d-9a16-1c5b3e2a4d77",
            "request_id": None,
            "principal": {
                "id": "op:omar",
                "type": "operator",
                "idp_sub": None,
                "display_name": "Omar",
            },
            "tenant_id": None,
            "deployment": {
                "id": "ota-omar-prod",
                "mode": "managed",
                "edition": "core",
                "version": "1.4.2",
            },
            "source": {"component": "conductor", "version": "1.4.2"},
            "payload": {
                "gate_id": "delete_email",
                "routine_id": "agentikey.inbox-triage",
                "proposed_action_hash": "sha256:abc123",
                "approval_mode": "approve_and_remember",
            },
            "redactions_applied": ["payload.user_email"],
        }
    )


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(
            {
                "schema_version": "1.0.0",
                "event_id": "01HXXX",
                "timestamp": datetime(2026, 5, 13, 14, 32),
                "event_type": "system.startup",
                "severity": "info",
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "principal": {"id": "system:bootstrap", "type": "system"},
                "deployment": {
                    "id": "x",
                    "mode": "vps",
                    "edition": "core",
                    "version": "0.1.0",
                },
                "source": {"component": "framework", "version": "0.1.0"},
            }
        )


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(
            {
                "schema_version": "1.0.0",
                "event_id": "01HXXX",
                "timestamp": datetime(2026, 5, 13, 14, 32, tzinfo=UTC),
                "event_type": "not.a.real.event",
                "severity": "info",
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "principal": {"id": "op:omar", "type": "operator"},
                "deployment": {
                    "id": "x",
                    "mode": "vps",
                    "edition": "core",
                    "version": "0.1.0",
                },
                "source": {"component": "framework", "version": "0.1.0"},
            }
        )


def test_termination_payload_full_example() -> None:
    RoutineRunTerminatedIncompletePayload.model_validate(
        {
            "cause": "hard_kill_timeout",
            "routine_id": "agentikey.inbox-triage",
            "routine_version": "1.4.2",
            "run_started_at": "2026-05-13T14:00:00Z",
            "run_terminated_at": "2026-05-13T14:15:00Z",
            "steps_completed": ["fetch_inbox", "classify_messages"],
            "steps_in_flight": ["generate_digest"],
            "steps_never_started": ["deliver_digest"],
            "gates_pending": [
                {
                    "gate_id": "delete_email",
                    "auto_rejected": True,
                    "reason": "routine_killed",
                }
            ],
            "artifacts_emitted": [
                {
                    "id": "classification.batch.0192fc83",
                    "status": "completed",
                    "stale_artifact_ttl": "4h",
                    "expires_at": "2026-05-13T18:15:00Z",
                },
                {
                    "id": "digest.draft.0192fc84",
                    "status": "failed",
                    "consumers": ["agentikey.morning-summary"],
                    "stale_artifact_ttl": "4h",
                    "expires_at": "2026-05-13T18:15:00Z",
                },
            ],
            "integration_calls_completed_during_termination": [
                {
                    "integration": "gmail",
                    "operation": "label_messages",
                    "count": 47,
                    "result": "succeeded",
                    "note": "Side effects retained; cannot be rolled back.",
                }
            ],
            "integration_calls_aborted": [
                {
                    "integration": "slack",
                    "operation": "chat.postMessage",
                    "state": "never_invoked",
                }
            ],
            "cleanup_recommendations": [
                "Review 47 Gmail labels applied during termination",
            ],
        }
    )
