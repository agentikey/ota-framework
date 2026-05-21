import pytest
from pydantic import ValidationError

from ota_core.contracts import (
    ChannelManifest,
    IntegrationDependency,
    KillListManifest,
    RoutineBundleManifest,
    RoutineVersion,
)


def _signature() -> dict[str, object]:
    return {
        "algorithm": "ed25519",
        "key_id": "agentikey-2026-05",
        "value": "base64-fake",
        "signed_fields": ["id"],
    }


def test_channel_manifest_full_example() -> None:
    ChannelManifest.model_validate(
        {
            "channel": {
                "id": "agentikey-prod",
                "schema_version": "1.0.0",
                "generated_at": "2026-05-13T12:00:00Z",
                "signing_key_id": "agentikey-2026-05",
                "next_signing_key_id": "agentikey-2026-06",
                "signature": _signature(),
            },
            "routines": [
                {
                    "id": "agentikey.inbox-triage",
                    "name": "Inbox Triage",
                    "description": "Triages inbox into action / read / archive",
                    "category": "productivity",
                    "deprecated": False,
                    "license": "agentikey-commercial-revocable-v1",
                    "versions": [
                        {
                            "version": "1.4.2",
                            "framework_compat": ">=1.3, <2.0",
                            "released_at": "2026-05-10T08:00:00Z",
                            "expires_at": "2027-05-10T08:00:00Z",
                            "bundle_url": "channel://agentikey/inbox-triage/1.4.2.tar.gz",
                            "bundle_sha256": "a" * 64,
                            "bundle_size_bytes": 14823,
                            "signature": _signature(),
                            "kill_status": "active",
                        }
                    ],
                }
            ],
        }
    )


def test_kill_list_manifest_full_example() -> None:
    KillListManifest.model_validate(
        {
            "schema_version": "1.0.0",
            "channel_id": "agentikey-prod",
            "generated_at": "2026-05-13T14:31:00Z",
            "signing_key_id": "agentikey-2026-05",
            "signature": _signature(),
            "entries": [
                {
                    "routine_id": "agentikey.inbox-triage",
                    "version": "1.4.2",
                    "kill_status": "emergency_killed",
                    "effective_at": "2026-05-13T14:30:00Z",
                    "reason_code": "compromised_signing_key",
                    "reason_summary": "Signing key compromised; revoke.",
                },
                {
                    "routine_id": "agentikey.calendar-prep",
                    "version": "0.9.1",
                    "kill_status": "hard_killed",
                    "effective_at": "2026-05-10T08:00:00Z",
                    "kill_grace_period": "15m",
                    "reason_code": "sunset",
                    "reason_summary": "EOL; replaced.",
                },
            ],
        }
    )


def test_kill_grace_period_rejected_on_non_hard_kill() -> None:
    with pytest.raises(ValidationError):
        RoutineVersion.model_validate(
            {
                "version": "1.0.0",
                "framework_compat": ">=1.0",
                "released_at": "2026-05-10T08:00:00Z",
                "expires_at": "2027-05-10T08:00:00Z",
                "bundle_url": "channel://x",
                "bundle_sha256": "a" * 64,
                "bundle_size_bytes": 1,
                "signature": _signature(),
                "kill_status": "active",
                "kill_grace_period": "15m",
            }
        )


def test_invalid_binding_kill_pair_rejected() -> None:
    with pytest.raises(ValidationError):
        IntegrationDependency.model_validate(
            {
                "id": "gmail",
                "binding_level": "client_shared",
                "on_emergency_kill": "burn_credential",
            }
        )


def test_routine_bundle_full_example() -> None:
    RoutineBundleManifest.model_validate(
        {
            "schema_version": "1.0.0",
            "id": "agentikey.inbox-triage",
            "version": "1.4.2",
            "framework_compat": ">=1.3, <2.0",
            "metadata": {
                "name": "Inbox Triage",
                "description": "Triages inbox",
                "author": "Agentikey",
                "author_url": "https://agentikey.com",
                "category": "productivity",
                "tags": ["email", "morning", "digest"],
            },
            "dependencies": {
                "routines": [
                    {
                        "id": "agentikey.identity-context",
                        "version_range": ">=1.0, <2.0",
                        "optional": False,
                    }
                ],
                "integrations": [
                    {
                        "id": "gmail",
                        "scopes": ["read", "label", "modify"],
                        "optional": False,
                        "binding_level": "routine_exclusive",
                        "on_emergency_kill": "burn_credential",
                    },
                    {
                        "id": "ms365",
                        "scopes": ["Mail.Read", "Calendar.Read"],
                        "optional": False,
                        "binding_level": "identity_bound",
                        "on_emergency_kill": "revoke_routine_grant",
                    },
                ],
            },
            "capabilities": {
                "provides": ["inbox.triage", "morning.digest"],
                "consumes": [],
            },
            "llm_requirements": {
                "schema_version": "1.0.0",
                "required": ["tool_use"],
                "preferred": ["prompt_caching", "parallel_tool_calls"],
                "min_context_tokens": 50_000,
                "cost_tier": "balanced",
                "pii_categories": ["contact_info", "communications"],
                "cache_pool": "productivity-shared",
                "cache_ttl": "5m",
                "budget": {"max_usd_per_run": 0.50},
            },
            "knobs": [
                {
                    "name": "digest_time",
                    "type": "time",
                    "default": "07:00",
                    "description": "When to deliver",
                    "timezone": "operator",
                },
                {
                    "name": "notify_threshold",
                    "type": "enum",
                    "values": ["high", "medium", "low", "off"],
                    "default": "high",
                    "description": "DM threshold",
                },
                {
                    "name": "include_promotions",
                    "type": "bool",
                    "default": False,
                    "description": "Promo tab",
                },
            ],
            "automation": {
                "cadence": [
                    {
                        "id": "morning_digest",
                        "cron": "0 7 * * *",
                        "timezone": "operator",
                        "action": "deliver_digest",
                        "on_missed": {"strategy": "run_if_within", "tolerance": "4h"},
                    }
                ],
                "events": [
                    {
                        "id": "incremental_classify",
                        "on": "integration.gmail.message_received",
                        "action": "classify_one",
                        "debounce": "30s",
                    }
                ],
            },
            "gates": [
                {
                    "id": "delete_email",
                    "description": "Confirm before permanent delete",
                    "approver_default": "operator",
                    "approval_modes": ["approve", "approve_and_remember", "tune_and_approve"],
                    "similarity_function": "subject_sender_hash",
                    "expires_after": "2h",
                }
            ],
            "state": {
                "shards": [{"name": "triage_state", "schema_url": "schemas/triage_state.json"}]
            },
            "artifacts": {"stale_artifact_ttl": "4h"},
            "files": [
                {"path": "system.md", "role": "system_prompt", "sha256": "a" * 64},
            ],
            "signature": _signature(),
        }
    )
