"""Shared fixtures for the binding-layer tests.

Builds a real `FilesystemIntegrationSource` pointed at
`tests/fixtures/adapters/` so the mock_messaging + mock_email adapters
discovered for the test session match what production code will see.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ota_connect.binding import (
    AdapterRegistry,
    BindingResolver,
    Bindings,
    DispatchContext,
)
from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.integration_source.source import FilesystemIntegrationSource
from ota_core.policy import L0bEnforcer

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "adapters"


def deployment_info() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def source_info() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


@pytest.fixture
def integration_source() -> FilesystemIntegrationSource:
    return FilesystemIntegrationSource([_FIXTURE_ROOT])


@pytest.fixture
def adapter_registry(integration_source: FilesystemIntegrationSource) -> AdapterRegistry:
    return AdapterRegistry(integration_source)


@pytest.fixture
def bindings() -> Bindings:
    return Bindings(capabilities={"messaging": "mock_messaging", "email": "mock_email"})


@pytest.fixture
def resolver(bindings: Bindings) -> BindingResolver:
    return BindingResolver(bindings)


@pytest.fixture
def dispatch_ctx(resolver: BindingResolver, adapter_registry: AdapterRegistry) -> DispatchContext:
    return DispatchContext(resolver=resolver, registry=adapter_registry)


@pytest.fixture
def audit_sink() -> NullAuditSink:
    return NullAuditSink(deployment=deployment_info(), source=source_info())


@pytest.fixture
def enforcer(audit_sink: NullAuditSink) -> L0bEnforcer:
    return L0bEnforcer(audit_sink=audit_sink)


@pytest.fixture(autouse=True)
def _reset_dispatch_ctx() -> Iterator[None]:
    from ota_connect.binding.dispatch import set_dispatch_context

    set_dispatch_context(None)
    yield
    set_dispatch_context(None)
