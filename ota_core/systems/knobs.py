from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ota_core.contracts.routine_source import (
    KnobBool,
    KnobCron,
    KnobDuration,
    KnobEnum,
    KnobFloat,
    KnobInt,
    KnobList,
    KnobString,
    KnobTime,
    RoutineBundleManifest,
)
from ota_core.systems.errors import KnobResolutionError


def resolve_knobs(
    manifest: RoutineBundleManifest,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    overrides = dict(overrides or {})
    resolved: dict[str, Any] = {}
    unknown = set(overrides.keys())
    for knob in manifest.knobs:
        unknown.discard(knob.name)
        if knob.name in overrides:
            resolved[knob.name] = _coerce(knob, overrides[knob.name])
            continue
        default = _default_for(knob)
        if default is _NO_DEFAULT:
            raise KnobResolutionError(
                f"knob {knob.name!r} of type {knob.type!r} has no default; supply an override"
            )
        resolved[knob.name] = default
    if unknown:
        raise KnobResolutionError(f"override(s) for unknown knob(s): {sorted(unknown)}")
    return resolved


class _NoDefault:
    __slots__ = ()


_NO_DEFAULT = _NoDefault()


def _default_for(knob: Any) -> Any:
    if isinstance(
        knob,
        KnobBool | KnobInt | KnobFloat | KnobString | KnobEnum | KnobTime | KnobDuration | KnobCron,
    ):
        return knob.default
    if isinstance(knob, KnobList):
        return list(knob.default)
    return _NO_DEFAULT


def _coerce(knob: Any, value: Any) -> Any:
    if isinstance(knob, KnobBool):
        if not isinstance(value, bool):
            raise KnobResolutionError(
                f"knob {knob.name!r}: expected bool, got {type(value).__name__}"
            )
        return value
    if isinstance(knob, KnobInt):
        if isinstance(value, bool) or not isinstance(value, int):
            raise KnobResolutionError(f"knob {knob.name!r}: expected int")
        if knob.min is not None and value < knob.min:
            raise KnobResolutionError(f"knob {knob.name!r}: {value} < min {knob.min}")
        if knob.max is not None and value > knob.max:
            raise KnobResolutionError(f"knob {knob.name!r}: {value} > max {knob.max}")
        return value
    if isinstance(knob, KnobFloat):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise KnobResolutionError(f"knob {knob.name!r}: expected float")
        value_f = float(value)
        if knob.min is not None and value_f < knob.min:
            raise KnobResolutionError(f"knob {knob.name!r}: {value_f} < min {knob.min}")
        if knob.max is not None and value_f > knob.max:
            raise KnobResolutionError(f"knob {knob.name!r}: {value_f} > max {knob.max}")
        return value_f
    if isinstance(knob, KnobString):
        if not isinstance(value, str):
            raise KnobResolutionError(f"knob {knob.name!r}: expected str")
        if knob.max_length is not None and len(value) > knob.max_length:
            raise KnobResolutionError(
                f"knob {knob.name!r}: length {len(value)} > max {knob.max_length}"
            )
        return value
    if isinstance(knob, KnobEnum):
        if value not in knob.values:
            raise KnobResolutionError(f"knob {knob.name!r}: value {value!r} not in {knob.values}")
        return value
    if isinstance(knob, KnobTime | KnobDuration | KnobCron):
        if not isinstance(value, str):
            raise KnobResolutionError(f"knob {knob.name!r}: expected str")
        return value
    if isinstance(knob, KnobList):
        if not isinstance(value, list):
            raise KnobResolutionError(f"knob {knob.name!r}: expected list")
        return list(value)
    return value
