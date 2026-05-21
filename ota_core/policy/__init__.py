from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def verb(
    *,
    idempotency: str,
    required_scopes: list[str],
    destructive: bool,
) -> Callable[[F], F]:
    """Placeholder decorator. Phase 2A.5 (L0b policy) replaces with real enforcement.

    Attaches the spec metadata to the wrapped function so the future L0b layer
    can read it without re-parsing vocabulary. Current behavior: identity.
    """

    def decorator(fn: F) -> F:
        fn._ota_verb_meta = {  # type: ignore[attr-defined]
            "idempotency": idempotency,
            "required_scopes": list(required_scopes),
            "destructive": destructive,
        }
        return fn

    return decorator
