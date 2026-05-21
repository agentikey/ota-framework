from __future__ import annotations


class IdentityProviderError(Exception):
    pass


class IdentityNotFoundError(IdentityProviderError):
    def __init__(self, handle: str, candidates: list[str] | None = None) -> None:
        self.handle = handle
        self.candidates = candidates or []
        super().__init__(f"identity not found: handle:@{handle}")


class IdentityAdapterMissingError(IdentityProviderError):
    def __init__(self, handle: str, adapter: str, available: list[str]) -> None:
        self.handle = handle
        self.adapter = adapter
        self.available = available
        super().__init__(
            f"identity handle:@{handle} has no mapping for adapter '{adapter}'; "
            f"available adapters: {available}"
        )


class IdentityAdapterMismatchError(IdentityProviderError):
    def __init__(self, ref_adapter: str, bound_adapter: str) -> None:
        self.ref_adapter = ref_adapter
        self.bound_adapter = bound_adapter
        super().__init__(
            f"raw:{ref_adapter}:... cannot be resolved by bound adapter '{bound_adapter}'"
        )


class MalformedIdentityRefError(IdentityProviderError):
    def __init__(self, ref: str, reason: str) -> None:
        self.ref = ref
        self.reason = reason
        super().__init__(f"malformed IdentityRef {ref!r}: {reason}")
