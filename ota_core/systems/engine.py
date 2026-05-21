from __future__ import annotations

import importlib.util
import inspect
import sys
import types
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ota_core.audit import AuditSink
from ota_core.contracts.audit_event import Principal
from ota_core.identity import IdentityProvider
from ota_core.observability import ObservabilitySink
from ota_core.policy import L0bEnforcer, RoutineRunContext
from ota_core.routine_source import RoutineBundle, RoutineSource
from ota_core.secrets import SecretsProvider
from ota_core.systems.errors import RoutineHelpersError, RoutineRunError
from ota_core.systems.knobs import resolve_knobs
from ota_core.trace import new_trace_id


@dataclass(frozen=True)
class Capability:
    """A bound capability the routine can call.

    Phase 2 placeholder. Phase 3 wires `callable` to the real adapter via
    the binding resolver + capability dispatch layer. For v0.1 tests the
    `callable` is a plain function or coroutine that the test supplies.
    """

    name: str
    callable: Callable[..., Any]
    integration_id: str | None = None


@dataclass
class RoutineRuntime:
    bundle: RoutineBundle
    context: RoutineRunContext
    knobs: Mapping[str, Any]
    identity: IdentityProvider
    secrets: SecretsProvider
    audit: AuditSink
    observability: ObservabilitySink
    capabilities: Mapping[str, Capability]

    def call(self, capability_name: str, *args: Any, **kwargs: Any) -> Any:
        cap = self.capabilities.get(capability_name)
        if cap is None:
            raise KeyError(
                f"capability {capability_name!r} not bound; available: "
                f"{sorted(self.capabilities.keys())}"
            )
        return cap.callable(*args, **kwargs)


@dataclass
class RoutineHandle:
    bundle: RoutineBundle
    helpers: types.ModuleType | None
    knobs: Mapping[str, Any]

    def main_callable(self) -> Callable[[RoutineRuntime], Any] | None:
        if self.helpers is None:
            return None
        candidate = getattr(self.helpers, "run", None)
        if candidate is None:
            return None
        if not callable(candidate):
            raise RoutineHelpersError(f"helpers.run for {self.bundle.id} is not callable")
        return candidate  # type: ignore[no-any-return]


@dataclass
class RoutineRunResult:
    routine_id: str
    routine_run_id: str
    trace_id: str
    started_at: str
    return_value: Any = None
    tool_calls_made: int = 0


class RoutineEngine:
    def __init__(
        self,
        *,
        routine_source: RoutineSource,
        identity_provider: IdentityProvider,
        secrets_provider: SecretsProvider,
        audit_sink: AuditSink,
        observability: ObservabilitySink,
        l0b: L0bEnforcer,
    ) -> None:
        self._source = routine_source
        self._identity = identity_provider
        self._secrets = secrets_provider
        self._audit = audit_sink
        self._observability = observability
        self._l0b = l0b

    def load(
        self,
        routine_id: str,
        *,
        knob_overrides: Mapping[str, Any] | None = None,
    ) -> RoutineHandle:
        bundle = self._source.load(routine_id)
        knobs = resolve_knobs(bundle.manifest, knob_overrides)
        helpers = _load_helpers(bundle)
        return RoutineHandle(bundle=bundle, helpers=helpers, knobs=knobs)

    async def run(
        self,
        handle: RoutineHandle,
        *,
        principal: Principal,
        capabilities: Mapping[str, Capability] | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
        trace_id: str | None = None,
    ) -> RoutineRunResult:
        main = handle.main_callable()
        if main is None:
            raise RoutineRunError(
                f"routine {handle.bundle.id} has no helpers.py with `run(runtime)` entry point"
            )

        bundle = handle.bundle
        allowed_integrations = frozenset(
            dep.id for dep in bundle.manifest.dependencies.integrations
        )
        declared_scopes = {
            dep.id: frozenset(dep.scopes) for dep in bundle.manifest.dependencies.integrations
        }
        ctx = RoutineRunContext(
            routine_id=bundle.id,
            routine_run_id=str(uuid.uuid4()),
            trace_id=trace_id if trace_id is not None else new_trace_id(),
            principal=principal,
            allowed_integrations=allowed_integrations,
            declared_scopes=declared_scopes,
            budget=bundle.manifest.llm_requirements.budget,
            request_id=request_id,
            tenant_id=tenant_id,
        )
        bound_capabilities = dict(capabilities or {})

        with self._l0b.routine_run(ctx) as run_ctx:
            with self._observability.span(
                "routine.run",
                attributes={"routine_id": bundle.id, "routine_run_id": run_ctx.routine_run_id},
            ):
                runtime = RoutineRuntime(
                    bundle=bundle,
                    context=run_ctx,
                    knobs=handle.knobs,
                    identity=self._identity,
                    secrets=self._secrets,
                    audit=self._audit,
                    observability=self._observability,
                    capabilities=bound_capabilities,
                )
                result = main(runtime)
                if inspect.isawaitable(result):
                    return_value = await result
                else:
                    return_value = result

        return RoutineRunResult(
            routine_id=bundle.id,
            routine_run_id=run_ctx.routine_run_id,
            trace_id=run_ctx.trace_id,
            started_at=run_ctx.trace_id,  # placeholder; full timing via observability span
            return_value=return_value,
            tool_calls_made=run_ctx.tool_calls_made,
        )


def _load_helpers(bundle: RoutineBundle) -> types.ModuleType | None:
    helpers_path = bundle.directory / "helpers.py"
    if not helpers_path.exists():
        return None
    module_name = f"ota_routines_dynamic.{bundle.id.replace('.', '_')}_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(module_name, helpers_path)
    if spec is None or spec.loader is None:
        raise RoutineHelpersError(f"cannot build spec for {helpers_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as e:
        sys.modules.pop(module_name, None)
        raise RoutineHelpersError(f"failed to import helpers.py for {bundle.id}: {e}") from e
    return module
