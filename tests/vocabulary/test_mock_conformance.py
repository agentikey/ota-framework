"""Smoke-tests the conformance harness itself by running it against the
mock adapters from `tests/fixtures/adapters/`. When real adapters land in
4A.3 / 4A.4 they reuse the same harness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ota_connect._types import ChannelRef, EmailThreadRef, ThreadRef
from ota_core.integration_source.source import FilesystemIntegrationSource
from tests.vocabulary.conformance import (
    ConformanceFixture,
    run_email_conformance,
    run_messaging_conformance,
)

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "adapters"


def _mock_impl(adapter_id: str) -> Any:
    from ota_connect.binding.registry import AdapterRegistry

    src = FilesystemIntegrationSource([_FIXTURE_ROOT])
    registry = AdapterRegistry(src)
    return registry.load(adapter_id, capability="messaging", verb="send_message").impl


def test_mock_messaging_adapter_passes_conformance() -> None:
    impl = _mock_impl("mock_messaging")
    fixture = ConformanceFixture(
        channel=ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging"),
        thread_ref=ThreadRef(
            id="T1",
            channel=ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging"),
            started_at=datetime.now(UTC),
            adapter="mock_messaging",
        ),
        recipients=["mailto:bob@example.com"],
    )
    run_messaging_conformance(impl, adapter_id="mock_messaging", fixture=fixture)


def test_mock_email_adapter_passes_conformance() -> None:
    src = FilesystemIntegrationSource([_FIXTURE_ROOT])
    from ota_connect.binding.registry import AdapterRegistry

    registry = AdapterRegistry(src)
    impl = registry.load("mock_email", capability="email", verb="send_email").impl
    fixture = ConformanceFixture(
        channel=ChannelRef(id="C1", kind="channel", name="general", adapter="mock_email"),
        thread_ref=None,
        recipients=["mailto:bob@example.com"],
        email_thread_ref=EmailThreadRef(
            id="T1", subject="Hi", started_at=datetime.now(UTC), adapter="mock_email"
        ),
    )
    run_email_conformance(impl, adapter_id="mock_email", fixture=fixture)
