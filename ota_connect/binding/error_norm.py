"""Error normalization — translate adapter exceptions to OTAConnectError.

The generated `ota_connect._types.errors` classes (Phase 1 codegen) declare
class-body annotations only — they have no `__init__`. That is a known
limitation (Phase 1 carry-forward note). Until codegen is updated, this
module constructs error instances by bypassing `__init__` and setting
attributes directly, then chaining the original adapter exception.

Usage:

    from ota_connect.binding.error_norm import normalize_adapter_errors

    with normalize_adapter_errors(adapter="slack", capability="messaging",
                                  verb="send_message"):
        return impl.invoke("messaging", "send_message", **kwargs)

Adapters can raise framework error types directly (e.g. `raise RateLimited(...)`
constructed via `make_error`); those pass through unchanged. Anything else
becomes `AdapterUnavailable(adapter=..., capability=..., verb=...,
retryable=True)` with the original exception chained.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from ota_connect._types.errors import AdapterUnavailable, OTAConnectError

E = TypeVar("E", bound=OTAConnectError)

_BASE_FIELDS = ("adapter", "capability", "verb", "retryable")


def make_error(cls: type[E], /, **fields: Any) -> E:
    """Construct an `OTAConnectError` subclass instance with attribute fields.

    The generated error classes don't have a synthesized `__init__`, so we
    instantiate via `__new__` and assign annotated fields. A reasonable
    `args[0]` is set on the underlying Exception so `str(e)` is informative.

    Required base fields: adapter, capability, verb. `retryable` defaults to
    False (or True for explicitly retryable subclasses that set a class-level
    default).
    """
    missing = [f for f in ("adapter", "capability", "verb") if f not in fields]
    if missing:
        raise TypeError(f"make_error({cls.__name__}): missing required fields: {missing}")
    err = cls.__new__(cls)
    if "retryable" not in fields:
        fields["retryable"] = bool(getattr(cls, "retryable", False))
    for key, value in fields.items():
        setattr(err, key, value)
    summary_extras = {k: v for k, v in fields.items() if k not in _BASE_FIELDS}
    if summary_extras:
        suffix = " " + " ".join(f"{k}={v!r}" for k, v in summary_extras.items())
    else:
        suffix = ""
    Exception.__init__(
        err,
        f"[{fields['adapter']}] {fields['capability']}.{fields['verb']}: {cls.__name__}{suffix}",
    )
    return err


@contextmanager
def normalize_adapter_errors(
    *,
    adapter: str,
    capability: str,
    verb: str,
) -> Iterator[None]:
    """Context manager: translate any non-`OTAConnectError` exception raised
    inside to `AdapterUnavailable` so routines only ever see framework errors.

    Adapters that want to raise specific framework errors (e.g.
    `RateLimited(retry_after=...)`) should call `make_error(RateLimited, ...)`
    themselves — those propagate through unchanged.
    """
    try:
        yield
    except OTAConnectError:
        raise
    except BaseException as exc:
        wrapped = make_error(
            AdapterUnavailable,
            adapter=adapter,
            capability=capability,
            verb=verb,
            retryable=True,
        )
        raise wrapped from exc
