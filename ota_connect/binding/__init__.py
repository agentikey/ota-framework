"""ota_connect.binding — capability dispatch + adapter binding layer.

Public surface (stable for routines + tests):

    from ota_connect.binding import (
        Bindings,
        BindingResolver,
        DispatchContext,
        dispatch_context,
        set_dispatch_context,
        AdapterRegistry,
        ActionRouter,
        InboundEmailLoop,
        assert_routine_install,
        validate_routine_install,
    )

Adapter authors implement `ota_connect.binding.AdapterImpl` and declare the
runtime entrypoint in their manifest (`AdapterManifest.entrypoint`).
"""

from ota_connect.binding.actions import (
    ActionEvent,
    ActionEventKind,
    ActionHandler,
    ActionRouter,
)
from ota_connect.binding.adapter_impl import AdapterImpl
from ota_connect.binding.bindings import Bindings
from ota_connect.binding.dispatch import (
    DispatchContext,
    NotConfiguredError,
    current_dispatch_context,
    dispatch_capability,
    dispatch_context,
    set_dispatch_context,
)
from ota_connect.binding.error_norm import make_error, normalize_adapter_errors
from ota_connect.binding.errors import (
    AdapterLoadError,
    AdapterNotFoundError,
    BindingError,
    CapabilityNotSatisfiedError,
    InstallValidationError,
    NoBindingError,
    VerbNotImplementedError,
)
from ota_connect.binding.inbound_email import InboundEmailLoop, RawInboundEvent
from ota_connect.binding.pagination import iter_all
from ota_connect.binding.registry import (
    AdapterFactory,
    AdapterRegistry,
    LoadedAdapter,
    find_adapter_for_capability,
)
from ota_connect.binding.resolver import BindingResolver, ResolvedBinding
from ota_connect.binding.validator import (
    ValidationReport,
    assert_routine_install,
    validate_routine_install,
)

__all__ = [
    "ActionEvent",
    "ActionEventKind",
    "ActionHandler",
    "ActionRouter",
    "AdapterFactory",
    "AdapterImpl",
    "AdapterLoadError",
    "AdapterNotFoundError",
    "AdapterRegistry",
    "BindingError",
    "BindingResolver",
    "Bindings",
    "CapabilityNotSatisfiedError",
    "DispatchContext",
    "InboundEmailLoop",
    "InstallValidationError",
    "LoadedAdapter",
    "NoBindingError",
    "NotConfiguredError",
    "RawInboundEvent",
    "ResolvedBinding",
    "ValidationReport",
    "VerbNotImplementedError",
    "assert_routine_install",
    "current_dispatch_context",
    "dispatch_capability",
    "dispatch_context",
    "find_adapter_for_capability",
    "iter_all",
    "make_error",
    "normalize_adapter_errors",
    "set_dispatch_context",
    "validate_routine_install",
]
