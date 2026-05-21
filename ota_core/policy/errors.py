from __future__ import annotations


class PolicyError(Exception):
    pass


class NotInRoutineRunError(PolicyError):
    pass


class IntegrationNotAllowedError(PolicyError):
    def __init__(self, integration_id: str, allowed: tuple[str, ...]) -> None:
        self.integration_id = integration_id
        self.allowed = allowed
        super().__init__(
            f"routine has no declared dependency on integration={integration_id!r}; "
            f"declared: {list(allowed)}"
        )


class ScopeEscalationError(PolicyError):
    def __init__(
        self,
        integration_id: str,
        missing: tuple[str, ...],
        declared: tuple[str, ...],
    ) -> None:
        self.integration_id = integration_id
        self.missing = missing
        self.declared = declared
        super().__init__(
            f"verb requires scopes outside routine declaration for integration={integration_id}: "
            f"missing={list(missing)}, declared={list(declared)}"
        )


class BudgetExceededError(PolicyError):
    def __init__(self, kind: str, limit: float, used: float, requested: float) -> None:
        self.kind = kind
        self.limit = limit
        self.used = used
        self.requested = requested
        super().__init__(
            f"budget {kind} exceeded: limit={limit}, used={used}, would-use={requested}"
        )
