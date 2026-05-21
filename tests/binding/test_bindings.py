from __future__ import annotations

import pytest
from pydantic import ValidationError

from ota_connect.binding import Bindings


def test_empty_bindings_validate() -> None:
    b = Bindings()
    assert b.capabilities == {}


def test_capability_and_verb_keys() -> None:
    b = Bindings(
        capabilities={
            "messaging": "slack",
            "messaging.send_email": "gmail",
            "email": "gmail",
        }
    )
    assert b.capabilities["messaging"] == "slack"
    assert b.capabilities["messaging.send_email"] == "gmail"


def test_key_pattern_rejects_uppercase() -> None:
    with pytest.raises(ValueError, match="must match"):
        Bindings(capabilities={"Messaging": "slack"})


def test_key_pattern_rejects_leading_digit() -> None:
    with pytest.raises(ValueError, match="must match"):
        Bindings(capabilities={"1capability": "slack"})


def test_key_pattern_rejects_dash() -> None:
    with pytest.raises(ValueError, match="must match"):
        Bindings(capabilities={"task-mgmt": "asana"})


def test_extra_top_level_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Bindings.model_validate({"capabilities": {}, "extra": "nope"})
