from __future__ import annotations

from ota_core.identity.errors import (
    IdentityAdapterMismatchError,
    IdentityAdapterMissingError,
    IdentityNotFoundError,
    IdentityProviderError,
    MalformedIdentityRefError,
)
from ota_core.identity.provider import (
    IdentityProvider,
    InMemoryIdentityProvider,
    LocalMarkdownIdentityProvider,
    Person,
    parse_identity_ref,
)

__all__ = [
    "IdentityAdapterMismatchError",
    "IdentityAdapterMissingError",
    "IdentityNotFoundError",
    "IdentityProvider",
    "IdentityProviderError",
    "InMemoryIdentityProvider",
    "LocalMarkdownIdentityProvider",
    "MalformedIdentityRefError",
    "Person",
    "parse_identity_ref",
]
