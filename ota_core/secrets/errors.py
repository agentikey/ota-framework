from __future__ import annotations


class SecretsProviderError(Exception):
    pass


class CredentialNotFoundError(SecretsProviderError):
    def __init__(self, integration_id: str, routine_id: str | None) -> None:
        self.integration_id = integration_id
        self.routine_id = routine_id
        scope = f"routine={routine_id}" if routine_id else "client-shared"
        super().__init__(f"no credential for integration={integration_id} ({scope})")


class InsufficientScopesError(SecretsProviderError):
    def __init__(
        self,
        integration_id: str,
        routine_id: str | None,
        requested: tuple[str, ...],
        granted: tuple[str, ...],
    ) -> None:
        self.integration_id = integration_id
        self.routine_id = routine_id
        self.requested = requested
        self.granted = granted
        missing = sorted(set(requested) - set(granted))
        super().__init__(
            f"credential for integration={integration_id} routine={routine_id} "
            f"missing scopes {missing}; granted={sorted(granted)}"
        )


class CredentialExpiredError(SecretsProviderError):
    def __init__(self, integration_id: str, routine_id: str | None) -> None:
        self.integration_id = integration_id
        self.routine_id = routine_id
        super().__init__(
            f"credential for integration={integration_id} routine={routine_id} has expired"
        )


class SecretsStoreCorruptError(SecretsProviderError):
    pass
