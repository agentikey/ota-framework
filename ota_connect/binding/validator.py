"""Install-time binding validator.

Implements the three install-time checks defined by `docs/architecture.md`
§3 Connect Binding layer plus the Contract C ↔ Contract D reconciliation
flagged as a Phase 1 / Phase 2 carry-forward (§16 cross-contract invariant 9
in architecture.md, §Validation rules in contracts.md).

Checks per routine:

1. Every capability the routine `requires:` (declared as `capabilities.consumes`
   or implied by a verb call site) has a binding in the client config.
2. Every bound adapter declares satisfaction of the required vocabulary
   version.
3. Every routine integration dependency exists in the active integration
   registry, the declared binding_level is supported by that integration,
   and the declared scopes are all present in the integration's
   `scope_vocabulary`.

Static identity-reference reachability (the third check from architecture
§3 — "every static-reachable handle resolves in people.md") belongs to the
routine bundle loader; this module only validates structural / cross-contract
shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from ota_connect.binding.errors import InstallValidationError
from ota_connect.binding.registry import AdapterRegistry
from ota_connect.binding.resolver import BindingResolver
from ota_core.contracts.integration_registry import IntegrationRegistryManifest
from ota_core.contracts.routine_source import RoutineBundleManifest


@dataclass(frozen=True)
class ValidationReport:
    routine_id: str
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_routine_install(
    manifest: RoutineBundleManifest,
    *,
    bindings_resolver: BindingResolver,
    adapter_registry: AdapterRegistry,
    integration_registry: IntegrationRegistryManifest,
    required_capabilities: list[str] | None = None,
) -> ValidationReport:
    """Run install-time validation. Returns a report (call `.ok` to branch).

    `required_capabilities` lets the caller pass the set of capabilities the
    routine's verb call-sites use, in addition to those declared in
    `capabilities.consumes`. The bundle loader collects both.
    """
    issues: list[str] = []
    declared_consumes = list(manifest.capabilities.consumes)
    required = sorted({*declared_consumes, *(required_capabilities or [])})

    issues.extend(_check_capability_bindings(required, bindings_resolver, adapter_registry))
    issues.extend(_check_integration_dependencies(manifest, integration_registry))
    return ValidationReport(routine_id=manifest.id, issues=issues)


def assert_routine_install(
    manifest: RoutineBundleManifest,
    *,
    bindings_resolver: BindingResolver,
    adapter_registry: AdapterRegistry,
    integration_registry: IntegrationRegistryManifest,
    required_capabilities: list[str] | None = None,
) -> None:
    """Run validation and raise `InstallValidationError` on any failure."""
    report = validate_routine_install(
        manifest,
        bindings_resolver=bindings_resolver,
        adapter_registry=adapter_registry,
        integration_registry=integration_registry,
        required_capabilities=required_capabilities,
    )
    if not report.ok:
        raise InstallValidationError(report.routine_id, report.issues)


def _check_capability_bindings(
    required: list[str],
    resolver: BindingResolver,
    registry: AdapterRegistry,
) -> list[str]:
    issues: list[str] = []
    known_ids = set(registry.known_adapter_ids())
    bundles_by_id = {b.adapter_id: b for b in registry.discover_all()}
    binding_keys = list(resolver.bindings.capabilities.keys())
    for capability in required:
        relevant_keys = [
            k for k in binding_keys if k == capability or k.startswith(capability + ".")
        ]
        if not relevant_keys:
            issues.append(
                f"capability {capability!r} required by routine but no binding "
                "declared under bindings.capabilities"
            )
            continue
        for key in relevant_keys:
            adapter_id = resolver.bindings.capabilities[key]
            if adapter_id not in known_ids:
                issues.append(
                    f"binding {key!r} -> {adapter_id!r} but adapter is not "
                    "discoverable from configured IntegrationSource roots"
                )
                continue
            bundle = bundles_by_id.get(adapter_id)
            if bundle is not None and not bundle.satisfies(capability):
                issues.append(
                    f"adapter {adapter_id!r} bound to {key!r} but its manifest "
                    f"does not claim capability {capability!r}"
                )
    return issues


def _check_integration_dependencies(
    manifest: RoutineBundleManifest,
    registry: IntegrationRegistryManifest,
) -> list[str]:
    issues: list[str] = []
    integrations_by_id = {i.id: i for i in registry.integrations}
    for dep in manifest.dependencies.integrations:
        integration = integrations_by_id.get(dep.id)
        if integration is None:
            issues.append(
                f"integration {dep.id!r} declared by routine but not present in "
                "active IntegrationRegistryManifest"
            )
            continue
        if dep.binding_level not in integration.supported_binding_levels:
            issues.append(
                f"integration {dep.id!r}: routine requested binding_level="
                f"{dep.binding_level!r} but integration supports only "
                f"{list(integration.supported_binding_levels)}"
            )
        vocab_ids = {s.id for s in integration.scope_vocabulary}
        for scope in dep.scopes:
            if scope not in vocab_ids:
                issues.append(
                    f"integration {dep.id!r}: requested scope {scope!r} not in "
                    "integration scope_vocabulary"
                )
    return issues
