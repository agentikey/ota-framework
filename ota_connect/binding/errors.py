"""Errors raised by the binding + dispatch layer.

These are framework-internal failures (no adapter bound, unknown verb, install
validation failure). Errors that adapters raise at runtime are normalized to
the `ota_connect._types.errors.OTAConnectError` hierarchy by
`ota_connect.binding.error_norm.normalize_adapter_errors`.
"""

from __future__ import annotations


class BindingError(Exception):
    """Base for binding-layer failures."""


class NoBindingError(BindingError):
    """No adapter is bound for the requested capability or verb."""

    def __init__(self, capability: str, verb: str) -> None:
        self.capability = capability
        self.verb = verb
        super().__init__(
            f"no binding for capability={capability!r} verb={verb!r}; "
            "add an entry under bindings.capabilities"
        )


class AdapterNotFoundError(BindingError):
    """A binding references an adapter_id that no IntegrationSource knows about."""

    def __init__(self, adapter_id: str, capability: str, verb: str) -> None:
        self.adapter_id = adapter_id
        self.capability = capability
        self.verb = verb
        super().__init__(
            f"binding for {capability}.{verb} -> {adapter_id!r}, but no adapter "
            "with that id is discoverable from the configured IntegrationSource roots"
        )


class CapabilityNotSatisfiedError(BindingError):
    """Adapter is bound but its manifest does not claim the capability/version."""

    def __init__(self, adapter_id: str, capability: str, required_version: str | None) -> None:
        self.adapter_id = adapter_id
        self.capability = capability
        self.required_version = required_version
        super().__init__(
            f"adapter {adapter_id!r} does not satisfy capability={capability!r} "
            f"(required_version={required_version!r})"
        )


class AdapterLoadError(BindingError):
    """The adapter manifest entrypoint failed to import or instantiate."""

    def __init__(self, adapter_id: str, entrypoint: str, cause: BaseException) -> None:
        self.adapter_id = adapter_id
        self.entrypoint = entrypoint
        self.cause = cause
        super().__init__(
            f"failed to load adapter {adapter_id!r} from entrypoint {entrypoint!r}: "
            f"{type(cause).__name__}: {cause}"
        )


class VerbNotImplementedError(BindingError):
    """Adapter loaded successfully but does not implement the requested verb."""

    def __init__(self, adapter_id: str, capability: str, verb: str) -> None:
        self.adapter_id = adapter_id
        self.capability = capability
        self.verb = verb
        super().__init__(f"adapter {adapter_id!r} does not implement {capability}.{verb!r}")


class InstallValidationError(BindingError):
    """Aggregated install-time validation failure with multiple sub-issues."""

    def __init__(self, routine_id: str, issues: list[str]) -> None:
        self.routine_id = routine_id
        self.issues = issues
        body = "\n  - ".join(issues)
        super().__init__(f"install validation failed for routine {routine_id!r}:\n  - {body}")
