"""Tests for the install-time binding validator (Phase 3.4)."""

from __future__ import annotations

from typing import Any

from ota_connect.binding import (
    AdapterRegistry,
    BindingResolver,
    Bindings,
    InstallValidationError,
    assert_routine_install,
    validate_routine_install,
)
from ota_core.contracts.integration_registry import IntegrationRegistryManifest
from ota_core.contracts.routine_source import RoutineBundleManifest


def _routine_manifest(
    *,
    consumes: list[str],
    integrations: list[dict[str, Any]],
) -> RoutineBundleManifest:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "id": "ota.test",
        "version": "0.1.0",
        "framework_compat": ">=0.1.0",
        "metadata": {
            "name": "T",
            "description": "",
            "author": "x",
            "author_url": "https://x",
            "category": "x",
            "tags": [],
        },
        "dependencies": {"routines": [], "integrations": integrations},
        "capabilities": {"provides": [], "consumes": consumes},
        "llm_requirements": {
            "schema_version": "1.0.0",
            "required": [],
            "preferred": [],
            "pii_categories": ["none"],
        },
        "knobs": [],
        "automation": {"cadence": [], "events": []},
        "gates": [],
        "state": {"shards": []},
        "artifacts": {"stale_artifact_ttl": "4h"},
        "files": [{"path": "x.md", "role": "asset", "sha256": "a" * 64}],
        "signature": {
            "algorithm": "ed25519",
            "key_id": "k",
            "value": "v",
            "signed_fields": ["id"],
        },
    }
    return RoutineBundleManifest.model_validate(payload)


def _integration_registry(
    *,
    integration_id: str = "mock.messaging",
    supported_binding_levels: list[str] | None = None,
    scope_vocab: list[str] | None = None,
) -> IntegrationRegistryManifest:
    levels = supported_binding_levels or ["routine_exclusive", "client_shared"]
    vocab = scope_vocab or ["messaging:send", "messaging:read"]
    revocation_for_level = {
        "routine_exclusive": {"burn_credential": {"local_only": True, "operator_message": "ok"}},
        "client_shared": {"revoke_routine_access": {"local_only": True, "operator_message": "ok"}},
        "identity_bound": {"revoke_routine_grant": {"local_only": True, "operator_message": "ok"}},
    }
    revocation = {level: revocation_for_level[level] for level in levels}
    payload: dict[str, Any] = {
        "registry": {
            "id": "test-registry",
            "schema_version": "1.0.0",
            "generated_at": "2026-05-01T00:00:00Z",
            "signing_key_id": "k",
            "signature": {
                "algorithm": "ed25519",
                "key_id": "k",
                "value": "v",
                "signed_fields": ["id"],
            },
        },
        "integrations": [
            {
                "id": integration_id,
                "version": "0.1.0",
                "framework_compat": ">=0.1.0",
                "kill_status": "active",
                "metadata": {"name": "Mock", "vendor": "internal"},
                "auth_styles": ["api_key"],
                "supported_binding_levels": levels,
                "default_binding_level": levels[0],
                "endpoints": {"base_url": "https://example.com"},
                "egress_patterns": ["example.com"],
                "scope_vocabulary": [{"id": s} for s in vocab],
                "rate_limits": {
                    "requests_per_second": 1,
                    "requests_per_minute": 10,
                },
                "revocation": revocation,
                "operations": [
                    {
                        "id": "send",
                        "endpoint": "POST /send",
                        "side_effect": "stateful_safe",
                        "required_scopes": ["messaging:send"],
                        "idempotent": True,
                    }
                ],
                "webhooks": [],
                "pii_handling": {"payload_contains_pii_default": False},
                "data_residency": {"provider_regions": []},
                "signature": {
                    "algorithm": "ed25519",
                    "key_id": "k",
                    "value": "v",
                    "signed_fields": ["id"],
                },
            }
        ],
    }
    return IntegrationRegistryManifest.model_validate(payload)


def test_valid_install_returns_no_issues(
    adapter_registry: AdapterRegistry,
) -> None:
    manifest = _routine_manifest(
        consumes=["messaging"],
        integrations=[
            {
                "id": "mock.messaging",
                "scopes": ["messaging:send"],
                "binding_level": "routine_exclusive",
                "on_emergency_kill": "burn_credential",
            }
        ],
    )
    resolver = BindingResolver(Bindings(capabilities={"messaging": "mock_messaging"}))
    registry = _integration_registry()
    report = validate_routine_install(
        manifest,
        bindings_resolver=resolver,
        adapter_registry=adapter_registry,
        integration_registry=registry,
    )
    assert report.ok, report.issues


def test_missing_capability_binding_rejected(
    adapter_registry: AdapterRegistry,
) -> None:
    """Phase 3 tracer-bullet (negative case): install validation rejects an
    install where a required capability has no bound adapter."""
    manifest = _routine_manifest(
        consumes=["calendar"],  # calendar binding not declared
        integrations=[],
    )
    resolver = BindingResolver(Bindings(capabilities={"messaging": "mock_messaging"}))
    registry = _integration_registry()
    report = validate_routine_install(
        manifest,
        bindings_resolver=resolver,
        adapter_registry=adapter_registry,
        integration_registry=registry,
    )
    assert not report.ok
    assert any("calendar" in issue for issue in report.issues)

    # assert_routine_install raises with the aggregated message
    try:
        assert_routine_install(
            manifest,
            bindings_resolver=resolver,
            adapter_registry=adapter_registry,
            integration_registry=registry,
        )
    except InstallValidationError as e:
        assert "calendar" in str(e)
    else:
        raise AssertionError("expected InstallValidationError")


def test_binding_points_to_unknown_adapter(adapter_registry: AdapterRegistry) -> None:
    manifest = _routine_manifest(consumes=["messaging"], integrations=[])
    resolver = BindingResolver(Bindings(capabilities={"messaging": "nonexistent_adapter"}))
    registry = _integration_registry()
    report = validate_routine_install(
        manifest,
        bindings_resolver=resolver,
        adapter_registry=adapter_registry,
        integration_registry=registry,
    )
    assert not report.ok
    assert any("nonexistent_adapter" in issue for issue in report.issues)


def test_integration_not_in_registry(adapter_registry: AdapterRegistry) -> None:
    manifest = _routine_manifest(
        consumes=["messaging"],
        integrations=[
            {
                "id": "made.up.integration",
                "scopes": [],
                "binding_level": "routine_exclusive",
                "on_emergency_kill": "burn_credential",
            }
        ],
    )
    resolver = BindingResolver(Bindings(capabilities={"messaging": "mock_messaging"}))
    registry = _integration_registry()
    report = validate_routine_install(
        manifest,
        bindings_resolver=resolver,
        adapter_registry=adapter_registry,
        integration_registry=registry,
    )
    assert not report.ok
    assert any("made.up.integration" in issue for issue in report.issues)


def test_unsupported_binding_level(adapter_registry: AdapterRegistry) -> None:
    manifest = _routine_manifest(
        consumes=["messaging"],
        integrations=[
            {
                "id": "mock.messaging",
                "scopes": [],
                "binding_level": "identity_bound",
                "on_emergency_kill": "revoke_routine_grant",
            }
        ],
    )
    resolver = BindingResolver(Bindings(capabilities={"messaging": "mock_messaging"}))
    # Registry only supports routine_exclusive + client_shared
    registry = _integration_registry(
        supported_binding_levels=["routine_exclusive", "client_shared"]
    )
    report = validate_routine_install(
        manifest,
        bindings_resolver=resolver,
        adapter_registry=adapter_registry,
        integration_registry=registry,
    )
    assert not report.ok
    assert any("identity_bound" in issue for issue in report.issues)


def test_scope_not_in_vocabulary(adapter_registry: AdapterRegistry) -> None:
    manifest = _routine_manifest(
        consumes=["messaging"],
        integrations=[
            {
                "id": "mock.messaging",
                "scopes": ["messaging:nonexistent"],
                "binding_level": "routine_exclusive",
                "on_emergency_kill": "burn_credential",
            }
        ],
    )
    resolver = BindingResolver(Bindings(capabilities={"messaging": "mock_messaging"}))
    registry = _integration_registry()
    report = validate_routine_install(
        manifest,
        bindings_resolver=resolver,
        adapter_registry=adapter_registry,
        integration_registry=registry,
    )
    assert not report.ok
    assert any("messaging:nonexistent" in issue for issue in report.issues)
