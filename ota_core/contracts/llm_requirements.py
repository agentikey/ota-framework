from __future__ import annotations

from typing import Annotated, Literal, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from ota_core.contracts.shared import CostTier, SemVer

StandardFeatureFlag = Literal[
    "tool_use",
    "parallel_tool_calls",
    "streaming",
    "prompt_caching",
    "extended_thinking",
    "computer_use",
    "citations",
    "vision",
    "pdf_input",
    "json_mode",
    "function_strict_schema",
    "local_inference",
]

StandardPIICategory = Literal[
    "none",
    "contact_info",
    "identifiers",
    "financial",
    "health",
    "biometric",
    "employment",
    "behavioral",
    "communications",
    "location",
]

CacheTTL = Literal["5m", "1h"]

_STANDARD_FEATURE_FLAGS: frozenset[str] = frozenset(get_args(StandardFeatureFlag))
_STANDARD_PII_CATEGORIES: frozenset[str] = frozenset(get_args(StandardPIICategory))


def _validate_feature_flag(v: str) -> str:
    if v in _STANDARD_FEATURE_FLAGS:
        return v
    if v.startswith("custom:") and len(v) > len("custom:"):
        return v
    raise ValueError(f"unknown feature flag {v!r}; must be a standard flag or 'custom:<name>'")


def _validate_pii_category(v: str) -> str:
    if v in _STANDARD_PII_CATEGORIES:
        return v
    if v.startswith("custom:") and len(v) > len("custom:"):
        return v
    raise ValueError(f"unknown PII category {v!r}; must be a standard category or 'custom:<name>'")


FeatureFlag = Annotated[str, AfterValidator(_validate_feature_flag)]
PIICategory = Annotated[str, AfterValidator(_validate_pii_category)]


class LLMBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_input_tokens_per_run: int | None = Field(default=None, gt=0)
    max_output_tokens_per_run: int | None = Field(default=None, gt=0)
    max_usd_per_run: float | None = Field(default=None, gt=0)


class LLMRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: SemVer
    required: list[FeatureFlag]
    preferred: list[FeatureFlag] = Field(default_factory=list)
    forbidden_without: list[FeatureFlag] = Field(default_factory=list)
    min_context_tokens: int = Field(default=32_000, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    cost_tier: CostTier = "balanced"
    model_preference: list[str] = Field(default_factory=list)
    pii_categories: list[PIICategory]
    data_residency: list[str] = Field(default_factory=list)
    cache_pool: str | None = None
    cache_ttl: CacheTTL = "5m"
    budget: LLMBudget | None = None
