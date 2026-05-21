import pytest
from pydantic import ValidationError

from ota_core.contracts import IntegrationDeclaration, IntegrationRegistryManifest


def _signature() -> dict[str, object]:
    return {
        "algorithm": "ed25519",
        "key_id": "agentikey-2026-05",
        "value": "base64-fake",
        "signed_fields": ["id"],
    }


def _gmail() -> dict[str, object]:
    return {
        "id": "gmail.googleapis.com",
        "version": "2.1.0",
        "framework_compat": ">=1.3, <2.0",
        "kill_status": "active",
        "metadata": {
            "name": "Gmail",
            "vendor": "Google",
            "vendor_url": "https://gmail.com",
            "category": "email",
            "description": "Read, label, send, and modify Gmail messages.",
        },
        "auth_styles": ["oauth2"],
        "supported_binding_levels": ["routine_exclusive", "identity_bound"],
        "default_binding_level": "identity_bound",
        "endpoints": {
            "base_url": "https://gmail.googleapis.com",
            "oauth2": {
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            },
        },
        "egress_patterns": [
            "gmail.googleapis.com",
            "oauth2.googleapis.com",
            "accounts.google.com",
            "openidconnect.googleapis.com",
        ],
        "scope_vocabulary": [
            {"id": "read", "oauth_value": "https://www.googleapis.com/auth/gmail.readonly"},
            {"id": "label", "oauth_value": "https://www.googleapis.com/auth/gmail.labels"},
            {"id": "modify", "oauth_value": "https://www.googleapis.com/auth/gmail.modify"},
            {"id": "send", "oauth_value": "https://www.googleapis.com/auth/gmail.send"},
            {
                "id": "full",
                "oauth_value": "https://mail.google.com/",
                "warns_on_grant": "Prefer narrower scopes",
            },
        ],
        "rate_limits": {
            "requests_per_second": 5,
            "requests_per_minute": 250,
            "backoff_strategy": "exponential_with_jitter",
            "retry_after_header": "Retry-After",
        },
        "revocation": {
            "routine_exclusive": {
                "burn_credential": {
                    "method": "POST",
                    "url": "https://oauth2.googleapis.com/revoke",
                    "body": "token=${credential.access_token}",
                    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                    "success_status": [200, 400],
                }
            },
            "identity_bound": {
                "revoke_routine_grant": {
                    "local_only": True,
                    "operator_message": "Visit https://myaccount.google.com/permissions",
                }
            },
        },
        "operations": [
            {
                "id": "list_messages",
                "endpoint": "GET /gmail/v1/users/{user_id}/messages",
                "side_effect": "read_only",
                "required_scopes": ["read"],
                "idempotent": True,
                "rate_limit_weight": 1,
            },
            {
                "id": "send_message",
                "endpoint": "POST /gmail/v1/users/{user_id}/messages/send",
                "side_effect": "stateful_destructive",
                "required_scopes": ["send"],
                "idempotent": False,
                "rate_limit_weight": 10,
                "pii_classes": ["contact_info", "communications"],
            },
        ],
        "webhooks": [
            {
                "id": "message_received",
                "receiver_path": "/webhooks/gmail/messages",
                "auth_style": "google_pubsub_push",
                "secret_ref": "secret:gmail_pubsub_token",
                "verification": {"method": "google_pubsub_signature"},
                "routes_to_event": "integration.gmail.message_received",
            }
        ],
        "pii_handling": {
            "payload_contains_pii_default": True,
            "pii_classes_possible": ["contact_info", "communications", "behavioral"],
            "response_body_in_audit": False,
        },
        "data_residency": {
            "provider_regions": ["us", "eu", "apac"],
            "operator_can_pin_region": False,
        },
        "signature": _signature(),
    }


def test_gmail_declaration_full_example() -> None:
    IntegrationDeclaration.model_validate(_gmail())


def test_registry_manifest_full_example() -> None:
    IntegrationRegistryManifest.model_validate(
        {
            "registry": {
                "id": "agentikey-integrations",
                "schema_version": "1.0.0",
                "generated_at": "2026-05-13T12:00:00Z",
                "signing_key_id": "agentikey-2026-05",
                "next_signing_key_id": "agentikey-2026-06",
                "signature": _signature(),
            },
            "integrations": [_gmail()],
        }
    )


def test_required_scope_missing_from_vocab_rejected() -> None:
    payload = _gmail()
    payload["operations"] = [
        {
            "id": "bogus",
            "endpoint": "GET /bogus",
            "side_effect": "read_only",
            "required_scopes": ["does_not_exist"],
            "idempotent": True,
            "rate_limit_weight": 1,
        }
    ]
    with pytest.raises(ValidationError):
        IntegrationDeclaration.model_validate(payload)


def test_duplicate_operation_id_rejected() -> None:
    payload = _gmail()
    payload["operations"] = [
        {
            "id": "x",
            "endpoint": "GET /a",
            "side_effect": "read_only",
            "required_scopes": ["read"],
            "idempotent": True,
            "rate_limit_weight": 1,
        },
        {
            "id": "x",
            "endpoint": "GET /b",
            "side_effect": "read_only",
            "required_scopes": ["read"],
            "idempotent": True,
            "rate_limit_weight": 1,
        },
    ]
    with pytest.raises(ValidationError):
        IntegrationDeclaration.model_validate(payload)


def test_revocation_missing_for_supported_binding_rejected() -> None:
    payload = _gmail()
    revocation = payload["revocation"]
    assert isinstance(revocation, dict)
    del revocation["identity_bound"]
    with pytest.raises(ValidationError):
        IntegrationDeclaration.model_validate(payload)


def test_default_binding_outside_supported_rejected() -> None:
    payload = _gmail()
    payload["default_binding_level"] = "client_shared"
    with pytest.raises(ValidationError):
        IntegrationDeclaration.model_validate(payload)
