from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from ota_core.policy.errors import (
    BudgetExceededError,
    IntegrationNotAllowedError,
    NotInRoutineRunError,
    PolicyError,
    ScopeEscalationError,
)
from ota_core.policy.l0a import DEFAULT_L0A_BASE, L0aPromptBuilder
from ota_core.policy.l0b import (
    L0bEnforcer,
    RoutineRunContext,
    active_context,
)

__all__ = [
    "DEFAULT_L0A_BASE",
    "BudgetExceededError",
    "IntegrationNotAllowedError",
    "L0aPromptBuilder",
    "L0bEnforcer",
    "NotInRoutineRunError",
    "PolicyError",
    "RoutineRunContext",
    "ScopeEscalationError",
    "active_context",
    "verb",
]

F = TypeVar("F", bound=Callable[..., Any])


def verb(
    *,
    idempotency: str,
    required_scopes: list[str],
    destructive: bool,
) -> Callable[[F], F]:
    """Decorator for capability verbs.

    Attaches `_ota_verb_meta` for downstream policy reads, and wraps the call
    so the L0b enforcer (when active) records tool_call.invoked /
    tool_call.succeeded / tool_call.failed audit events. Outside a routine
    run context the wrapper is transparent — tests and ad-hoc calls work
    unchanged.
    """
    meta = {
        "idempotency": idempotency,
        "required_scopes": list(required_scopes),
        "destructive": destructive,
    }

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            active = active_context()
            if active is None:
                return fn(*args, **kwargs)
            enforcer, _ctx = active
            complete = enforcer.record_verb_invocation(
                verb_name=fn.__name__,
                verb_meta=meta,
                kwargs=kwargs,
            )
            try:
                result = fn(*args, **kwargs)
            except BaseException as e:
                complete(False, e)
                raise
            complete(True, None)
            return result

        wrapper._ota_verb_meta = meta  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
