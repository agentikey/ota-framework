from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ota_core.contracts.llm_requirements import LLMRequirements
from ota_core.contracts.shared import (
    VALID_BINDING_KILL_PAIRS,
    AwareDatetime,
    BindingLevel,
    KillStatus,
    OnEmergencyKill,
    ReverseDNS,
    SemVer,
    Sha256Hex,
    Signature,
)

ReasonCode = Literal[
    "sunset",
    "deprecated",
    "license_expired",
    "compromised_signing_key",
    "malicious_update_detected",
    "data_leak_in_progress",
    "vulnerability_disclosed",
    "contract_terminated",
]

ApprovalMode = Literal["approve", "approve_and_remember", "tune_and_approve"]
GateKind = Literal["preview", "confidence", "diff", "permission", "budget", "novelty"]
FileRole = Literal["system_prompt", "step", "gate_template", "state_schema", "asset"]
OnMissedStrategy = Literal["coalesce", "skip", "run_all", "run_if_within"]


class RoutineVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: SemVer
    framework_compat: str = Field(min_length=1)
    released_at: AwareDatetime
    expires_at: AwareDatetime
    bundle_url: str = Field(min_length=1)
    bundle_sha256: Sha256Hex
    bundle_size_bytes: int = Field(gt=0)
    signature: Signature
    changelog_url: str | None = None
    kill_status: KillStatus
    kill_grace_period: str | None = None

    @model_validator(mode="after")
    def _kill_grace_only_for_hard_killed(self) -> RoutineVersion:
        if self.kill_grace_period is not None and self.kill_status != "hard_killed":
            raise ValueError("kill_grace_period is only valid when kill_status == 'hard_killed'")
        return self


class RoutineCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ReverseDNS
    name: str = Field(min_length=1)
    description: str = ""
    category: str = ""
    deprecated: bool = False
    license: str = ""
    versions: list[RoutineVersion] = Field(min_length=1)


class ChannelHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    schema_version: SemVer
    generated_at: AwareDatetime
    signing_key_id: str = Field(min_length=1)
    next_signing_key_id: str | None = None
    signature: Signature


class ChannelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: ChannelHeader
    routines: list[RoutineCatalogEntry] = Field(default_factory=list)


class KillListEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routine_id: ReverseDNS
    version: SemVer
    kill_status: KillStatus
    effective_at: AwareDatetime
    reason_code: ReasonCode
    reason_summary: str = Field(min_length=1)
    kill_grace_period: str | None = None

    @model_validator(mode="after")
    def _kill_grace_only_for_hard_killed(self) -> KillListEntry:
        if self.kill_grace_period is not None and self.kill_status != "hard_killed":
            raise ValueError("kill_grace_period is only valid when kill_status == 'hard_killed'")
        return self


class KillListManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    channel_id: str = Field(min_length=1)
    generated_at: AwareDatetime
    signing_key_id: str = Field(min_length=1)
    signature: Signature
    entries: list[KillListEntry] = Field(default_factory=list)


class RoutineDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ReverseDNS
    version_range: str = Field(min_length=1)
    optional: bool = False


class IntegrationDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    scopes: list[str] = Field(default_factory=list)
    optional: bool = False
    binding_level: BindingLevel
    on_emergency_kill: OnEmergencyKill

    @model_validator(mode="after")
    def _binding_kill_pair_valid(self) -> IntegrationDependency:
        pair = (self.binding_level, self.on_emergency_kill)
        if pair not in VALID_BINDING_KILL_PAIRS:
            raise ValueError(f"invalid (binding_level, on_emergency_kill) pair: {pair}")
        return self


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provides: list[str] = Field(default_factory=list)
    consumes: list[str] = Field(default_factory=list)


class Dependencies(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routines: list[RoutineDependency] = Field(default_factory=list)
    integrations: list[IntegrationDependency] = Field(default_factory=list)


class _KnobBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""


class KnobBool(_KnobBase):
    type: Literal["bool"]
    default: bool


class KnobInt(_KnobBase):
    type: Literal["int"]
    default: int
    min: int | None = None
    max: int | None = None


class KnobFloat(_KnobBase):
    type: Literal["float"]
    default: float
    min: float | None = None
    max: float | None = None


class KnobString(_KnobBase):
    type: Literal["string"]
    default: str
    max_length: int | None = Field(default=None, gt=0)
    pattern: str | None = None


class KnobEnum(_KnobBase):
    type: Literal["enum"]
    values: list[str] = Field(min_length=1)
    default: str


class KnobTime(_KnobBase):
    type: Literal["time"]
    default: str = Field(pattern=r"^\d{2}:\d{2}$")
    timezone: str = "operator"


class KnobDuration(_KnobBase):
    type: Literal["duration"]
    default: str = Field(min_length=1)


class KnobCron(_KnobBase):
    type: Literal["cron"]
    default: str = Field(min_length=1)
    timezone: str = "operator"


class KnobSecretRef(_KnobBase):
    type: Literal["secret_ref"]


class KnobIntegrationRef(_KnobBase):
    type: Literal["integration_ref"]


class KnobList(_KnobBase):
    type: Literal["list"]
    inner_type: Literal["bool", "int", "float", "string", "enum", "time", "duration", "cron"]
    default: list[bool | int | float | str] = Field(default_factory=list)


Knob = Annotated[
    KnobBool
    | KnobInt
    | KnobFloat
    | KnobString
    | KnobEnum
    | KnobTime
    | KnobDuration
    | KnobCron
    | KnobSecretRef
    | KnobIntegrationRef
    | KnobList,
    Field(discriminator="type"),
]


class AutomationCadence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    timezone: str = "operator"
    action: str = Field(min_length=1)
    on_missed: OnMissedPolicy | None = None


class OnMissedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: OnMissedStrategy
    tolerance: str | None = None


class AutomationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    on: str = Field(min_length=1)
    action: str = Field(min_length=1)
    debounce: str | None = None


class Automation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cadence: list[AutomationCadence] = Field(default_factory=list)
    events: list[AutomationEvent] = Field(default_factory=list)


class Gate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = ""
    kind: GateKind | None = None
    approver_default: str = "operator"
    approval_modes: list[ApprovalMode] = Field(min_length=1)
    similarity_function: str | None = None
    expires_after: str | None = None


class StateShard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    schema_url: str = Field(min_length=1)


class StateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shards: list[StateShard] = Field(default_factory=list)


class ArtifactsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stale_artifact_ttl: str = "4h"


class FileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    role: FileRole
    sha256: Sha256Hex


class RoutineMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    author: str = ""
    author_url: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)


class RoutineBundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    id: ReverseDNS
    version: SemVer
    framework_compat: str = Field(min_length=1)
    metadata: RoutineMetadata
    dependencies: Dependencies = Field(default_factory=Dependencies)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    llm_requirements: LLMRequirements
    knobs: list[Knob] = Field(default_factory=list)
    automation: Automation = Field(default_factory=Automation)
    gates: list[Gate] = Field(default_factory=list)
    state: StateConfig = Field(default_factory=StateConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)
    files: list[FileEntry] = Field(min_length=1)
    signature: Signature


AutomationCadence.model_rebuild()
