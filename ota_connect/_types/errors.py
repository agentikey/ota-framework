# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from datetime import timedelta


class OTAConnectError(Exception):
    """Base for all errors raised from ota_connect.* capabilities."""

    adapter: str  # which adapter raised
    capability: str  # which capability
    verb: str  # which verb
    retryable: bool  # framework retry hint (not a guarantee)


class IdentityResolveError(OTAConnectError):
    """The IdentityRef could not be resolved for the bound adapter."""

    handle: str
    candidates: list[str]  # fuzzy-match suggestions, if IdentityProvider supports them


class AdapterMismatchError(OTAConnectError):
    """A ref produced by adapter A was passed to a verb bound to adapter B."""

    ref_adapter: str
    bound_adapter: str


class RecipientUnreachable(OTAConnectError):
    """Recipient exists but cannot be delivered to (deactivated, DMs disabled, etc.)."""

    reason: str


class RateLimited(OTAConnectError):
    """Upstream rate-limited; framework will retry per adapter policy."""

    retry_after: timedelta | None
    retryable: bool = True


class MessageRejected(OTAConnectError):
    """Adapter accepted arguments but upstream refused (content filter, policy, etc.)."""

    reason: str


class AdapterUnavailable(OTAConnectError):
    """Adapter cannot reach upstream (network failure, auth expired, etc.)."""

    retryable: bool = True


class CapabilityDegraded(OTAConnectError):
    """The bound adapter does not satisfy this verb's required scopes or feature level."""

    missing_scope: str | None = None
    missing_feature: str | None = None
