from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ota_core.contracts.shared import DeploymentMode, Edition, SemVer, Severity

IdentityProviderType = Literal["local", "oidc_social", "oidc_enterprise", "saml"]
_CORE_IDENTITY_TYPES: frozenset[str] = frozenset({"local", "oidc_social"})

SecretsProviderType = Literal["encrypted_file", "env", "vault", "aws_sm", "azure_kv", "gcp_sm"]
_CORE_SECRETS_TYPES: frozenset[str] = frozenset({"encrypted_file", "env"})

AuditSinkType = Literal["jsonl_local", "splunk_hec", "datadog", "s3_immutable", "syslog", "kafka"]
_CORE_AUDIT_SINKS: frozenset[str] = frozenset({"jsonl_local"})

ObservabilitySinkType = Literal["local_otel", "none", "otlp"]
_CORE_OBSERVABILITY_SINKS: frozenset[str] = frozenset({"local_otel", "none"})

LLMProviderType = Literal[
    "anthropic_direct",
    "gemini_direct",
    "ollama_local",
    "custom_gateway",
    "bedrock",
    "azure_openai",
    "vertex",
]
_CORE_LLM_PROVIDERS: frozenset[str] = frozenset(
    {"anthropic_direct", "gemini_direct", "ollama_local"}
)

RoutineSourceType = Literal[
    "agentikey_private_channel",
    "local_directory",
    "agentikey_mirrored_channel",
    "agentikey_approval_gate",
    "pinned_version_source",
]
_CORE_ROUTINE_SOURCES: frozenset[str] = frozenset({"agentikey_private_channel", "local_directory"})

LocalInferenceMode = Literal["disabled", "external_ollama", "embedded_sidecar"]
EgressMode = Literal["open", "allowlist", "none"]
BudgetOnExceeded = Literal["pause_non_critical_routines", "pause_all_routines", "notify_only"]
DigestCadence = Literal["daily", "weekly", "monthly"]
RateLimitOnExceeded = Literal["coalesce_into_summary", "drop", "delay"]
StormDetectionAction = Literal["suppress_individual_emit_single_summary", "drop"]
NotificationChannelType = Literal["slack_dm", "email", "pagerduty", "push"]


class BootstrapIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: IdentityProviderType
    principal_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    email: str | None = None


class OperatorSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bootstrap_identity: BootstrapIdentity


class IdentityProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: IdentityProviderType


class SecretsProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: SecretsProviderType
    master_key_source: str | None = None


class AuditProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    sink: AuditSinkType
    retention_days: int = Field(default=90, gt=0)
    rotation: Literal["daily", "weekly", "monthly", "never"] = "daily"


class ObservabilityProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    sink: ObservabilitySinkType
    endpoint: str | None = None
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)


class LLMEndpointConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: LLMProviderType
    api_key_ref: str | None = None
    default_model: str = Field(min_length=1)
    region: str = ""


class LLMProvidersConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: LLMEndpointConfig
    fallback: LLMEndpointConfig | None = None


class RoutineSourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: RoutineSourceType
    channel_url: str | None = None
    refresh_token_ref: str | None = None
    public_key_pem_ref: str | None = None
    poll_interval: str = "1h"
    kill_list_poll_interval: str = "60s"
    directory_path: str | None = None


class IntegrationRegistrySourceConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: RoutineSourceType
    channel_url: str | None = None
    refresh_token_ref: str | None = None
    public_key_pem_ref: str | None = None
    poll_interval: str = "1h"
    kill_list_poll_interval: str = "60s"
    directory_path: str | None = None


class Providers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: IdentityProviderConfig
    secrets: SecretsProviderConfig
    audit: AuditProviderConfig
    observability: ObservabilityProviderConfig
    llm: LLMProvidersConfig
    routine_source: RoutineSourceConfig
    integration_registry: IntegrationRegistrySourceConfig


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    timeout: str = "10s"


class SidecarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1)
    auto_pull_on_first_start: bool = True
    gpu_passthrough: bool = False
    max_tokens_per_request: int = Field(default=512, gt=0)


class LocalInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: LocalInferenceMode = "disabled"
    ollama: OllamaConfig | None = None
    sidecar: SidecarConfig | None = None

    @model_validator(mode="after")
    def _mode_implies_subconfig(self) -> LocalInferenceConfig:
        if self.mode == "external_ollama" and self.ollama is None:
            raise ValueError("local_inference.mode='external_ollama' requires ollama block")
        if self.mode == "embedded_sidecar" and self.sidecar is None:
            raise ValueError("local_inference.mode='embedded_sidecar' requires sidecar block")
        return self


class EgressConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: EgressMode = "allowlist"
    additional_allowlist: list[str] = Field(default_factory=list)


class ProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    http: str | None = None
    https: str | None = None
    no_proxy: list[str] = Field(default_factory=list)


class TLSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ca_bundle_path: str | None = None
    client_cert_path: str | None = None
    client_key_ref: str | None = None


class WebhookReceiverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bind_address: str = "0.0.0.0"
    port: int = Field(default=8443, gt=0, le=65535)
    tls_cert_path: str | None = None
    tls_key_ref: str | None = None
    public_url: str | None = None


class NetworkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    egress: EgressConfig = Field(default_factory=EgressConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    tls: TLSConfig = Field(default_factory=TLSConfig)
    user_agent: str = Field(min_length=1)
    webhook_receiver: WebhookReceiverConfig | None = None


class NotificationChannel(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: NotificationChannelType
    user: str | None = None
    address: str | None = None
    token_ref: str | None = None
    service_key_secret: str | None = None


class DigestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = Field(min_length=1)
    cadence: DigestCadence


class AcknowledgementConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool
    timeout: str = "5m"
    escalation_chain: list[str] = Field(default_factory=list)


class SeverityRouting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery: list[str] = Field(default_factory=list)
    digest: DigestConfig | None = None
    acknowledgement: AcknowledgementConfig | None = None


class PerRoutineRateLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: str = "10m"
    max_notifications: int = Field(default=5, ge=1)
    on_exceeded: RateLimitOnExceeded = "coalesce_into_summary"


class StormDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window: str = "5m"
    threshold_events_same_type: int = Field(default=20, ge=1)
    action: StormDetectionAction = "suppress_individual_emit_single_summary"


class NotificationRateLimiting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    per_routine_per_event_type: PerRoutineRateLimit = Field(default_factory=PerRoutineRateLimit)
    storm_detection: StormDetection = Field(default_factory=StormDetection)


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    channels: dict[str, NotificationChannel]
    routing: dict[Severity, SeverityRouting]
    rate_limiting: NotificationRateLimiting = Field(default_factory=NotificationRateLimiting)

    @model_validator(mode="after")
    def _routing_covers_all_severities(self) -> NotificationsConfig:
        required: set[str] = set(get_args(Severity)) - {"debug"}
        missing = required - set(self.routing.keys())
        if missing:
            raise ValueError(
                "notifications.routing must cover info/warn/error/critical; "
                f"missing: {sorted(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _delivery_channels_exist(self) -> NotificationsConfig:
        channel_names = set(self.channels.keys()) | {"dashboard", "push", "pager"}
        for sev, rule in self.routing.items():
            for ch in rule.delivery:
                if ch not in channel_names:
                    raise ValueError(f"routing[{sev!r}].delivery references unknown channel {ch!r}")
        return self


class GlobalBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_usd_per_day: float = Field(gt=0)
    max_input_tokens_per_day: int = Field(gt=0)
    on_exceeded: BudgetOnExceeded = "pause_non_critical_routines"


class PerRoutineBudgetDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_usd_per_run: float = Field(gt=0)
    max_input_tokens_per_run: int = Field(gt=0)


class ResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_budget: GlobalBudget
    per_routine_budget_default: PerRoutineBudgetDefault


class FeatureFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_local_inference: bool = False
    enable_pii_redaction: bool = True
    enable_drift_monitoring: bool = True
    enable_crash_loop_detection: bool = True


class DeploymentHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    id: str = Field(min_length=1)
    mode: DeploymentMode
    edition: Edition
    framework_version: SemVer
    region: str = Field(min_length=1)
    tenant_id: str | None = None


class DeploymentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment: DeploymentHeader
    operator: OperatorSection
    providers: Providers
    local_inference: LocalInferenceConfig = Field(default_factory=LocalInferenceConfig)
    network: NetworkConfig
    notifications: NotificationsConfig
    resource_limits: ResourceLimits
    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)

    @model_validator(mode="after")
    def _edition_gates_provider_types(self) -> DeploymentConfig:
        if self.deployment.edition != "core":
            return self
        gates: list[tuple[str, str, frozenset[str]]] = [
            ("identity.type", self.providers.identity.type, _CORE_IDENTITY_TYPES),
            ("secrets.type", self.providers.secrets.type, _CORE_SECRETS_TYPES),
            ("audit.sink", self.providers.audit.sink, _CORE_AUDIT_SINKS),
            (
                "observability.sink",
                self.providers.observability.sink,
                _CORE_OBSERVABILITY_SINKS,
            ),
            (
                "llm.primary.provider",
                self.providers.llm.primary.provider,
                _CORE_LLM_PROVIDERS,
            ),
            (
                "routine_source.type",
                self.providers.routine_source.type,
                _CORE_ROUTINE_SOURCES,
            ),
            (
                "integration_registry.type",
                self.providers.integration_registry.type,
                _CORE_ROUTINE_SOURCES,
            ),
        ]
        if self.providers.llm.fallback is not None:
            gates.append(
                (
                    "llm.fallback.provider",
                    self.providers.llm.fallback.provider,
                    _CORE_LLM_PROVIDERS,
                )
            )
        for path, picked, allowed in gates:
            if picked not in allowed:
                raise ValueError(
                    f"providers.{path}={picked!r} is Enterprise-only; "
                    f"deployment.edition='core' only allows {sorted(allowed)}"
                )
        return self

    @model_validator(mode="after")
    def _local_inference_flag_consistent(self) -> DeploymentConfig:
        flag = self.feature_flags.enable_local_inference
        enabled = self.local_inference.mode != "disabled"
        if flag != enabled:
            raise ValueError(
                f"feature_flags.enable_local_inference={flag} but "
                f"local_inference.mode={self.local_inference.mode!r}"
            )
        return self
