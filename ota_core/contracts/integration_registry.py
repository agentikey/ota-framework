from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator

from ota_core.contracts.llm_requirements import PIICategory
from ota_core.contracts.shared import (
    VALID_BINDING_KILL_PAIRS,
    AuthStyle,
    AwareDatetime,
    BindingLevel,
    KillStatus,
    OnEmergencyKill,
    ReverseDNS,
    SemVer,
    Signature,
)

BackoffStrategy = Literal["exponential_with_jitter", "linear", "constant"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
SideEffectClass = Literal["read_only", "stateful_safe", "stateful_destructive"]
WebhookVerificationMethod = Literal[
    "hmac-sha256",
    "shared_secret",
    "jwt",
    "google_pubsub_signature",
]


class IntegrationRegistryHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    schema_version: SemVer
    generated_at: AwareDatetime
    signing_key_id: str = Field(min_length=1)
    next_signing_key_id: str | None = None
    signature: Signature


class IntegrationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    vendor: str = ""
    vendor_url: str = ""
    category: str = ""
    description: str = ""


class OAuth2Endpoints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorize_url: str = Field(min_length=1)
    token_url: str = Field(min_length=1)
    userinfo_url: str | None = None


class IntegrationEndpoints(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_url: str = Field(min_length=1)
    oauth2: OAuth2Endpoints | None = None


class ScopeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    oauth_value: str = ""
    description: str = ""
    warns_on_grant: str | None = None


class PerOperationRateOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1)
    requests_per_second: int | None = Field(default=None, gt=0)
    requests_per_minute: int | None = Field(default=None, gt=0)


class RateLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests_per_second: int = Field(gt=0)
    requests_per_minute: int = Field(gt=0)
    burst_capacity: int | None = Field(default=None, gt=0)
    backoff_strategy: BackoffStrategy = "exponential_with_jitter"
    retry_after_header: str = "Retry-After"
    max_retries: int = Field(default=5, ge=0)
    per_operation_overrides: list[PerOperationRateOverride] = Field(default_factory=list)


class RemoteRevocationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: HttpMethod
    url: str = Field(min_length=1)
    body: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    success_status: list[int] = Field(min_length=1)


class LocalOnlyRevocationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_only: Literal[True]
    operator_message: str = Field(min_length=1)


def _revocation_tag(v: Any) -> str:
    if isinstance(v, LocalOnlyRevocationAction):
        return "local"
    if isinstance(v, RemoteRevocationAction):
        return "remote"
    if isinstance(v, dict):
        return "local" if v.get("local_only") is True else "remote"
    raise TypeError(f"cannot tag revocation action of type {type(v).__name__}")


RevocationAction = Annotated[
    Annotated[RemoteRevocationAction, Tag("remote")]
    | Annotated[LocalOnlyRevocationAction, Tag("local")],
    Discriminator(_revocation_tag),
]


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    endpoint: str = Field(min_length=1, pattern=r"^[A-Z]+ /.+$")
    side_effect: SideEffectClass
    required_scopes: list[str] = Field(default_factory=list)
    idempotent: bool
    rate_limit_weight: int = Field(default=1, ge=1)
    pii_classes: list[PIICategory] = Field(default_factory=list)
    auth_style: AuthStyle | None = None
    arguments_schema_ref: str | None = None


class WebhookVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: WebhookVerificationMethod
    algorithm: str | None = None
    header: str | None = None


class Webhook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    receiver_path: str = Field(pattern=r"^/.+")
    auth_style: str = Field(min_length=1)
    secret_ref: str = Field(min_length=1)
    verification: WebhookVerification
    routes_to_event: str = Field(min_length=1)


class PIIHandling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_contains_pii_default: bool = False
    pii_classes_possible: list[PIICategory] = Field(default_factory=list)
    response_body_in_audit: bool = False


class IntegrationDataResidency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_regions: list[str] = Field(default_factory=list)
    operator_can_pin_region: bool = False


class IntegrationDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ReverseDNS
    version: SemVer
    framework_compat: str = Field(min_length=1)
    kill_status: KillStatus
    metadata: IntegrationMetadata
    auth_styles: list[AuthStyle] = Field(min_length=1)
    supported_binding_levels: list[BindingLevel] = Field(min_length=1)
    default_binding_level: BindingLevel
    endpoints: IntegrationEndpoints
    egress_patterns: list[str] = Field(min_length=1)
    scope_vocabulary: list[ScopeEntry] = Field(default_factory=list)
    rate_limits: RateLimits
    revocation: dict[BindingLevel, dict[OnEmergencyKill, RevocationAction]]
    operations: list[Operation] = Field(min_length=1)
    webhooks: list[Webhook] = Field(default_factory=list)
    pii_handling: PIIHandling
    data_residency: IntegrationDataResidency
    signature: Signature

    @model_validator(mode="after")
    def _default_binding_in_supported(self) -> IntegrationDeclaration:
        if self.default_binding_level not in self.supported_binding_levels:
            raise ValueError(
                f"default_binding_level {self.default_binding_level!r} "
                f"not in supported_binding_levels {self.supported_binding_levels!r}"
            )
        return self

    @model_validator(mode="after")
    def _revocation_covers_supported(self) -> IntegrationDeclaration:
        for level in self.supported_binding_levels:
            if level not in self.revocation:
                raise ValueError(f"revocation missing entry for binding_level={level!r}")
            valid_actions = {a for (b, a) in VALID_BINDING_KILL_PAIRS if b == level}
            for action in self.revocation[level]:
                if action not in valid_actions:
                    raise ValueError(
                        f"revocation[{level!r}] declares {action!r}, "
                        f"which is not a valid on_emergency_kill for that binding"
                    )
        return self

    @model_validator(mode="after")
    def _operations_required_scopes_in_vocab(self) -> IntegrationDeclaration:
        vocab_ids = {entry.id for entry in self.scope_vocabulary}
        for op in self.operations:
            for scope in op.required_scopes:
                if scope not in vocab_ids:
                    raise ValueError(
                        f"operation {op.id!r} requires scope {scope!r} "
                        f"not declared in scope_vocabulary"
                    )
        return self

    @model_validator(mode="after")
    def _operation_ids_unique(self) -> IntegrationDeclaration:
        seen: set[str] = set()
        for op in self.operations:
            if op.id in seen:
                raise ValueError(f"duplicate operation id: {op.id!r}")
            seen.add(op.id)
        return self


class IntegrationRegistryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry: IntegrationRegistryHeader
    integrations: list[IntegrationDeclaration] = Field(default_factory=list)
