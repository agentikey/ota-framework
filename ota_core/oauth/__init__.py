"""OAuth 2.0 helpers shared by `ota_connect` adapters.

Two surfaces:

* `OAuthClient` — provider-agnostic Authorization Code flow. Generates auth
  URLs, exchanges callback codes for tokens, refreshes when expired, and
  persists tokens via the `SecretsProvider` seam (Phase 1).
* `OAuthTokenStore` — thin wrapper around `SecretsProvider` that normalizes
  Slack / Gmail / generic provider token records into a single shape so
  adapters can look up an access token with `store.access_token(integration_id,
  routine_id)`.

The module deliberately stays small. It does not bake in PKCE, JWT, or
device-flow paths — those land as new providers when an integration needs
them. It also does not own HTTP transport: tests pass an `httpx.AsyncClient`
or `httpx.Client` so they can be mocked with `pytest-httpx`.
"""

from ota_core.oauth.client import (
    AuthorizationRequest,
    OAuthClient,
    OAuthError,
    OAuthState,
    OAuthTokenResponse,
)
from ota_core.oauth.token_store import OAuthTokenStore, TokenRecord

__all__ = [
    "AuthorizationRequest",
    "OAuthClient",
    "OAuthError",
    "OAuthState",
    "OAuthTokenResponse",
    "OAuthTokenStore",
    "TokenRecord",
]
