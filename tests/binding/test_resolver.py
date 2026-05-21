from __future__ import annotations

import pytest

from ota_connect.binding import BindingResolver, Bindings, NoBindingError


def _resolver(mapping: dict[str, str]) -> BindingResolver:
    return BindingResolver(Bindings(capabilities=mapping))


def test_capability_default_resolves() -> None:
    r = _resolver({"messaging": "slack"})
    assert r.resolve("messaging", "send_message").adapter_id == "slack"
    assert r.resolve("messaging", "send_message").matched_key == "messaging"


def test_verb_override_wins_over_capability_default() -> None:
    r = _resolver({"messaging": "slack", "messaging.send_email": "gmail"})
    out = r.resolve("messaging", "send_email")
    assert out.adapter_id == "gmail"
    assert out.matched_key == "messaging.send_email"


def test_unrelated_verb_falls_back_to_capability_default() -> None:
    r = _resolver({"messaging": "slack", "messaging.send_email": "gmail"})
    out = r.resolve("messaging", "send_message")
    assert out.adapter_id == "slack"
    assert out.matched_key == "messaging"


def test_no_binding_raises() -> None:
    r = _resolver({"messaging": "slack"})
    with pytest.raises(NoBindingError) as exc_info:
        r.resolve("calendar", "create_event")
    assert exc_info.value.capability == "calendar"
    assert exc_info.value.verb == "create_event"


def test_try_resolve_returns_none() -> None:
    r = _resolver({"messaging": "slack"})
    assert r.try_resolve("calendar", "create_event") is None


def test_disjoint_prefixes_dont_collide() -> None:
    r = _resolver(
        {
            "messaging": "slack",
            "messaging_thread": "x",
            "messaging.send_email": "gmail",
        }
    )
    assert r.resolve("messaging", "send_message").adapter_id == "slack"
    assert r.resolve("messaging", "send_email").adapter_id == "gmail"
    assert r.resolve("messaging_thread", "anything").adapter_id == "x"


def test_longest_prefix_match_with_three_levels() -> None:
    r = _resolver(
        {
            "messaging": "default_adapter",
            "messaging.send_email": "gmail",
            "messaging.send_email.priority": "ses",
        }
    )
    assert r.resolve("messaging", "send_email").adapter_id == "gmail"
    assert r.resolve("messaging", "send_email.priority").adapter_id == "ses"
