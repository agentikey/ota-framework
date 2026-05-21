import pytest
from pydantic import ValidationError

from ota_core.contracts import LLMRequirements


def test_full_example_from_contracts_md() -> None:
    LLMRequirements.model_validate(
        {
            "schema_version": "1.0.0",
            "required": ["tool_use"],
            "preferred": ["prompt_caching", "parallel_tool_calls"],
            "forbidden_without": [],
            "min_context_tokens": 50_000,
            "max_output_tokens": 4096,
            "cost_tier": "balanced",
            "model_preference": ["claude-sonnet-4-6", "claude-haiku-4-5"],
            "pii_categories": ["contact_info", "communications"],
            "data_residency": [],
            "cache_pool": "productivity-shared",
            "cache_ttl": "5m",
            "budget": {
                "max_input_tokens_per_run": 80_000,
                "max_output_tokens_per_run": 4096,
                "max_usd_per_run": 0.50,
            },
        }
    )


def test_custom_feature_flag_accepted() -> None:
    LLMRequirements.model_validate(
        {
            "schema_version": "1.0.0",
            "required": ["custom:my_extension"],
            "pii_categories": ["none"],
        }
    )


def test_unknown_feature_flag_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequirements.model_validate(
            {
                "schema_version": "1.0.0",
                "required": ["not_a_real_flag"],
                "pii_categories": ["none"],
            }
        )


def test_zero_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequirements.model_validate(
            {
                "schema_version": "1.0.0",
                "required": [],
                "pii_categories": ["none"],
                "budget": {"max_usd_per_run": 0},
            }
        )


def test_unknown_pii_category_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMRequirements.model_validate(
            {
                "schema_version": "1.0.0",
                "required": [],
                "pii_categories": ["totally_made_up"],
            }
        )
