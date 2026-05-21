"""Capability dispatch — the runtime glue between generated verbs and adapters.

Flow when a routine calls e.g. `ota_connect.messaging.send_message(...)`:

1. The generated verb in `ota_connect/messaging/verbs.py` is wrapped by the
   `@verb` decorator from `ota_core.policy`. The decorator emits
   `tool_call.invoked` (and later `tool_call.succeeded` / `tool_call.failed`)
   audit events when an L0b run context is active.
2. The verb body calls `dispatch("send_message", **locals())` in
   `ota_connect/messaging/dispatch.py`, which forwards to this module's
   `dispatch_capability("messaging", "send_message", ...)`.
3. We look up the active dispatch context (per-call set by the routine engine
   when the framework boots), resolve the binding via longest-prefix-match,
   load the adapter, and run the call inside the error-normalization context.
4. Before invoking the adapter we call `L0bEnforcer.enforce_integration` and
   `enforce_scopes` so any policy violation aborts before side effects.

The dispatch context is set via `set_dispatch_context(ctx)` early in
framework boot (typically from `ota_core.systems.system`). Tests use the
`dispatch_context()` context manager to install one for the duration of a
test. Calling a verb without a dispatch context raises `NotConfiguredError`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from ota_connect.binding.error_norm import normalize_adapter_errors
from ota_connect.binding.errors import (
    BindingError,
    VerbNotImplementedError,
)
from ota_connect.binding.registry import AdapterRegistry
from ota_connect.binding.resolver import BindingResolver
from ota_core.policy import active_context


class NotConfiguredError(RuntimeError):
    """Dispatch was called but no DispatchContext is installed."""


@dataclass(frozen=True)
class DispatchContext:
    resolver: BindingResolver
    registry: AdapterRegistry


_ACTIVE: ContextVar[DispatchContext | None] = ContextVar(
    "ota_connect_dispatch_active", default=None
)


def set_dispatch_context(ctx: DispatchContext | None) -> None:
    """Install a global dispatch context (called once at framework boot)."""
    _ACTIVE.set(ctx)


def current_dispatch_context() -> DispatchContext | None:
    return _ACTIVE.get()


@contextmanager
def dispatch_context(ctx: DispatchContext) -> Iterator[DispatchContext]:
    """Scoped install of a DispatchContext — used by tests and the routine engine."""
    token = _ACTIVE.set(ctx)
    try:
        yield ctx
    finally:
        _ACTIVE.reset(token)


def _verb_required_scopes(capability: str, verb: str) -> tuple[str, ...]:
    """Read the `_ota_verb_meta` attached by `@verb` to the generated function."""
    try:
        module = __import__(f"ota_connect.{capability}.verbs", fromlist=[verb])
    except ImportError:
        return ()
    fn = getattr(module, verb, None)
    if fn is None:
        return ()
    meta = getattr(fn, "_ota_verb_meta", None) or {}
    return tuple(meta.get("required_scopes", ()))


def dispatch_capability(
    capability: str,
    verb: str,
    /,
    **kwargs: Any,
) -> Any:
    """Dispatch a capability verb to its bound adapter.

    The generated verb's `@verb` decorator owns the tool_call.* audit events.
    This function adds the integration / scope enforcement and the actual
    adapter invocation.
    """
    ctx = _ACTIVE.get()
    if ctx is None:
        raise NotConfiguredError(
            f"ota_connect.{capability}.{verb} called but no DispatchContext is "
            "installed; framework boot must call ota_connect.binding.dispatch."
            "set_dispatch_context(...) before the first verb call"
        )

    resolved = ctx.resolver.resolve(capability, verb)
    loaded = ctx.registry.load(resolved.adapter_id, capability=capability, verb=verb)

    active = active_context()
    if active is not None:
        enforcer, _run_ctx = active
        enforcer.enforce_integration(loaded.integration_id)
        required_scopes = _verb_required_scopes(capability, verb)
        if required_scopes:
            enforcer.enforce_scopes(loaded.integration_id, required_scopes)

    with normalize_adapter_errors(
        adapter=resolved.adapter_id,
        capability=capability,
        verb=verb,
    ):
        try:
            return loaded.impl.invoke(capability, verb, **kwargs)
        except BindingError:
            raise
        except AttributeError as exc:
            if "invoke" in str(exc):
                raise VerbNotImplementedError(
                    adapter_id=resolved.adapter_id, capability=capability, verb=verb
                ) from exc
            raise
        except NotImplementedError as exc:
            raise VerbNotImplementedError(
                adapter_id=resolved.adapter_id, capability=capability, verb=verb
            ) from exc
