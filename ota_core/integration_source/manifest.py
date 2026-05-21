from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ota_core.contracts.shared import AuthStyle, SemVer


class AdapterCapabilityClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: str = Field(min_length=1)
    version: SemVer


class AdapterManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    adapter_id: str = Field(min_length=1)
    integration_id: str = Field(min_length=1)
    version: SemVer
    framework_compat: str = Field(min_length=1)
    capabilities: list[AdapterCapabilityClaim] = Field(min_length=1)
    auth_styles: list[AuthStyle] = Field(default_factory=list)
    entrypoint: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
