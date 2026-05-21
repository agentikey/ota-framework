from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

KillStatus = Literal["active", "soft_killed", "hard_killed", "emergency_killed"]
BindingLevel = Literal["routine_exclusive", "client_shared", "identity_bound"]
OnEmergencyKill = Literal["burn_credential", "revoke_routine_access", "revoke_routine_grant"]
AuthStyle = Literal["oauth2", "api_key", "webhook_secret", "mtls", "custom"]
SideEffect = Literal["read_only", "stateful_safe", "stateful_destructive"]
Severity = Literal["debug", "info", "warn", "error", "critical"]
CostTier = Literal["cheap", "balanced", "premium", "local"]
Edition = Literal["core", "enterprise"]
DeploymentMode = Literal["local", "vps", "managed"]
SignatureAlgorithm = Literal["ed25519"]


VALID_BINDING_KILL_PAIRS: frozenset[tuple[BindingLevel, OnEmergencyKill]] = frozenset(
    {
        ("routine_exclusive", "burn_credential"),
        ("client_shared", "revoke_routine_access"),
        ("identity_bound", "revoke_routine_grant"),
    }
)


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_REVERSE_DNS_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z0-9][a-z0-9.-]*$")
_SHA256_RE = re.compile(r"^(sha256[:-])?[a-f0-9]{64}$")


def _validate_semver(v: str) -> str:
    if not _SEMVER_RE.match(v):
        raise ValueError(f"not a valid semver: {v!r}")
    return v


def _validate_reverse_dns(v: str) -> str:
    if not _REVERSE_DNS_RE.match(v):
        raise ValueError(f"not a reverse-DNS identifier: {v!r}")
    return v


def _validate_sha256(v: str) -> str:
    if not _SHA256_RE.match(v):
        raise ValueError(f"not a sha256 hex digest: {v!r}")
    return v


def _validate_aware_datetime(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (RFC 3339 / ISO 8601 with TZ)")
    return v


SemVer = Annotated[str, AfterValidator(_validate_semver)]
ReverseDNS = Annotated[str, AfterValidator(_validate_reverse_dns)]
Sha256Hex = Annotated[str, AfterValidator(_validate_sha256)]
AwareDatetime = Annotated[datetime, AfterValidator(_validate_aware_datetime)]


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm: SignatureAlgorithm
    key_id: str = Field(min_length=1)
    value: str = Field(min_length=1)
    signed_fields: list[str] = Field(min_length=1)
