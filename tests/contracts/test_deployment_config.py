import copy

import pytest
from pydantic import ValidationError

from ota_core.contracts import DeploymentConfig


def _config() -> dict[str, object]:
    return {
        "deployment": {
            "schema_version": "1.0.0",
            "id": "ota-omar-prod",
            "mode": "managed",
            "edition": "core",
            "framework_version": "1.4.2",
            "region": "us",
            "tenant_id": None,
        },
        "operator": {
            "bootstrap_identity": {
                "type": "local",
                "principal_id": "op:omar",
                "display_name": "Omar",
                "email": "omar@agentikey.com",
            }
        },
        "providers": {
            "identity": {"type": "local"},
            "secrets": {
                "type": "encrypted_file",
                "master_key_source": "keychain://ota/master-key",
            },
            "audit": {
                "sink": "jsonl_local",
                "retention_days": 90,
                "rotation": "daily",
            },
            "observability": {"sink": "local_otel", "sample_rate": 1.0},
            "llm": {
                "primary": {
                    "provider": "anthropic_direct",
                    "api_key_ref": "secret:anthropic_api_key",
                    "default_model": "claude-sonnet-4-6",
                    "region": "us",
                },
                "fallback": {
                    "provider": "anthropic_direct",
                    "api_key_ref": "secret:anthropic_api_key_backup",
                    "default_model": "claude-haiku-4-5",
                },
            },
            "routine_source": {
                "type": "agentikey_private_channel",
                "channel_url": "https://channel.agentikey.com/v1",
                "refresh_token_ref": "secret:agentikey_refresh_token",
                "public_key_pem_ref": "config:agentikey_pubkey_2026",
                "poll_interval": "1h",
                "kill_list_poll_interval": "60s",
            },
            "integration_registry": {
                "type": "agentikey_private_channel",
                "channel_url": "https://integrations.agentikey.com/v1",
                "refresh_token_ref": "secret:agentikey_integrations_refresh_token",
                "public_key_pem_ref": "config:agentikey_pubkey_2026",
                "poll_interval": "1h",
                "kill_list_poll_interval": "60s",
            },
        },
        "local_inference": {"mode": "disabled"},
        "network": {
            "egress": {"mode": "allowlist", "additional_allowlist": []},
            "proxy": {"http": None, "https": None, "no_proxy": ["localhost", "127.0.0.1"]},
            "tls": {},
            "user_agent": "OneTrueAgent-Core/1.4.2",
        },
        "notifications": {
            "schema_version": "1.0.0",
            "channels": {
                "primary_slack": {"type": "slack_dm", "user": "U0123456"},
                "primary_email": {"type": "email", "address": "omar@agentikey.com"},
            },
            "routing": {
                "info": {"delivery": ["dashboard"]},
                "warn": {
                    "delivery": ["dashboard"],
                    "digest": {"channel": "primary_email", "cadence": "weekly"},
                },
                "error": {"delivery": ["primary_slack", "dashboard"]},
                "critical": {
                    "delivery": ["primary_slack", "dashboard"],
                    "acknowledgement": {
                        "required": True,
                        "timeout": "5m",
                        "escalation_chain": ["primary_slack", "primary_email"],
                    },
                },
            },
        },
        "resource_limits": {
            "global_budget": {
                "max_usd_per_day": 100.0,
                "max_input_tokens_per_day": 10_000_000,
                "on_exceeded": "pause_non_critical_routines",
            },
            "per_routine_budget_default": {
                "max_usd_per_run": 1.0,
                "max_input_tokens_per_run": 80_000,
            },
        },
        "feature_flags": {
            "enable_local_inference": False,
            "enable_pii_redaction": True,
            "enable_drift_monitoring": True,
            "enable_crash_loop_detection": True,
        },
    }


def test_full_example_from_contracts_md() -> None:
    DeploymentConfig.model_validate(_config())


def test_enterprise_only_provider_in_core_rejected() -> None:
    payload = copy.deepcopy(_config())
    providers = payload["providers"]
    assert isinstance(providers, dict)
    providers["secrets"] = {"type": "vault"}
    with pytest.raises(ValidationError):
        DeploymentConfig.model_validate(payload)


def test_local_inference_flag_inconsistent_rejected() -> None:
    payload = copy.deepcopy(_config())
    feature_flags = payload["feature_flags"]
    assert isinstance(feature_flags, dict)
    feature_flags["enable_local_inference"] = True
    with pytest.raises(ValidationError):
        DeploymentConfig.model_validate(payload)


def test_missing_routing_severity_rejected() -> None:
    payload = copy.deepcopy(_config())
    notifications = payload["notifications"]
    assert isinstance(notifications, dict)
    routing = notifications["routing"]
    assert isinstance(routing, dict)
    del routing["critical"]
    with pytest.raises(ValidationError):
        DeploymentConfig.model_validate(payload)


def test_routing_references_unknown_channel_rejected() -> None:
    payload = copy.deepcopy(_config())
    notifications = payload["notifications"]
    assert isinstance(notifications, dict)
    routing = notifications["routing"]
    assert isinstance(routing, dict)
    routing["error"] = {"delivery": ["channel_that_does_not_exist"]}
    with pytest.raises(ValidationError):
        DeploymentConfig.model_validate(payload)


def test_external_ollama_requires_ollama_block() -> None:
    payload = copy.deepcopy(_config())
    payload["local_inference"] = {"mode": "external_ollama"}
    feature_flags = payload["feature_flags"]
    assert isinstance(feature_flags, dict)
    feature_flags["enable_local_inference"] = True
    with pytest.raises(ValidationError):
        DeploymentConfig.model_validate(payload)
