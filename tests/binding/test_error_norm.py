from __future__ import annotations

from datetime import timedelta

import pytest

from ota_connect._types.errors import (
    AdapterUnavailable,
    OTAConnectError,
    RateLimited,
    RecipientUnreachable,
)
from ota_connect.binding import make_error, normalize_adapter_errors


def test_make_error_assigns_base_fields() -> None:
    err = make_error(
        AdapterUnavailable,
        adapter="mock",
        capability="messaging",
        verb="send_message",
    )
    assert err.adapter == "mock"
    assert err.capability == "messaging"
    assert err.verb == "send_message"
    assert err.retryable is True  # AdapterUnavailable defaults retryable to True
    assert isinstance(err, OTAConnectError)
    assert isinstance(err, Exception)
    assert "messaging.send_message" in str(err)


def test_make_error_with_subclass_specific_field() -> None:
    err = make_error(
        RateLimited,
        adapter="slack",
        capability="messaging",
        verb="send_message",
        retry_after=timedelta(seconds=30),
    )
    assert err.retry_after == timedelta(seconds=30)
    assert err.retryable is True


def test_make_error_missing_base_field_raises() -> None:
    with pytest.raises(TypeError, match="missing required fields"):
        make_error(AdapterUnavailable, capability="messaging", verb="send_message")


def test_normalize_passes_through_ota_connect_errors() -> None:
    sentinel = make_error(
        RecipientUnreachable,
        adapter="slack",
        capability="messaging",
        verb="send_message",
        reason="dms_disabled",
    )

    with pytest.raises(RecipientUnreachable) as exc_info:
        with normalize_adapter_errors(adapter="slack", capability="messaging", verb="send_message"):
            raise sentinel
    assert exc_info.value is sentinel


def test_normalize_wraps_other_exceptions() -> None:
    with pytest.raises(AdapterUnavailable) as exc_info:
        with normalize_adapter_errors(adapter="slack", capability="messaging", verb="send_message"):
            raise RuntimeError("upstream barf")
    err = exc_info.value
    assert err.adapter == "slack"
    assert err.capability == "messaging"
    assert err.verb == "send_message"
    assert err.retryable is True
    assert isinstance(err.__cause__, RuntimeError)
