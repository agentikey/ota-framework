from __future__ import annotations


class IntegrationSourceError(Exception):
    pass


class AdapterManifestNotFoundError(IntegrationSourceError):
    pass


class AdapterDiscoveryError(IntegrationSourceError):
    pass


class DuplicateAdapterError(IntegrationSourceError):
    def __init__(self, adapter_id: str, paths: list[str]) -> None:
        self.adapter_id = adapter_id
        self.paths = paths
        super().__init__(f"duplicate adapter_id {adapter_id} in: {paths}")
