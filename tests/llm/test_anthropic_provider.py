from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ota_core.llm import (
    AnthropicProvider,
    LLMProvider,
    LLMRequest,
    Message,
    TextBlock,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
)


@dataclass
class FakeMessages:
    captured: dict[str, Any] = field(default_factory=dict)
    response: Any = None

    async def create(self, **kwargs: Any) -> Any:
        self.captured = kwargs
        return self.response


@dataclass
class FakeClient:
    messages: FakeMessages = field(default_factory=FakeMessages)
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


def _fake_response(
    *,
    model: str = "claude-sonnet-4-6",
    content: list[Any] | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> Any:
    return SimpleNamespace(
        model=model,
        content=content or [SimpleNamespace(type="text", text="Hello")],
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        ),
    )


def _provider(fake: FakeClient | None = None) -> tuple[AnthropicProvider, FakeClient]:
    client = fake or FakeClient()
    provider = AnthropicProvider(client=cast(Any, client), region="us")
    return provider, client


def test_provider_satisfies_protocol() -> None:
    provider, _ = _provider()
    assert isinstance(provider, AnthropicProvider)
    _: LLMProvider = provider


def test_supports_known_flags() -> None:
    provider, _ = _provider()
    assert provider.supports("tool_use")
    assert provider.supports("prompt_caching")
    assert provider.supports("vision")


def test_supports_rejects_unsupported_flag() -> None:
    provider, _ = _provider()
    assert not provider.supports("function_strict_schema")
    assert not provider.supports("local_inference")


def test_max_context_tokens_known_model() -> None:
    provider, _ = _provider()
    assert provider.max_context_tokens("claude-sonnet-4-6") == 200_000
    assert provider.max_context_tokens("claude-opus-4-7[1m]") == 1_000_000


def test_max_context_tokens_unknown_model_default() -> None:
    provider, _ = _provider()
    assert provider.max_context_tokens("some-future-model") == 200_000


def test_metadata() -> None:
    provider, _ = _provider()
    meta = provider.metadata()
    assert meta.name == "anthropic_direct"
    assert meta.region == "us"


async def test_create_message_string_content_translates() -> None:
    client = FakeClient()
    client.messages.response = _fake_response()
    provider, _ = _provider(client)

    response = await provider.create_message(
        LLMRequest(
            model="claude-sonnet-4-6",
            messages=[Message(role="user", content="Hello")],
            max_tokens=1024,
            system="You are helpful",
        )
    )

    assert client.messages.captured["model"] == "claude-sonnet-4-6"
    assert client.messages.captured["max_tokens"] == 1024
    assert client.messages.captured["system"] == "You are helpful"
    assert client.messages.captured["messages"] == [{"role": "user", "content": "Hello"}]
    assert response.model == "claude-sonnet-4-6"
    assert response.stop_reason == "end_turn"
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 50
    assert len(response.content) == 1
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == "Hello"


async def test_create_message_tool_use_roundtrip() -> None:
    client = FakeClient()
    client.messages.response = _fake_response(
        content=[
            SimpleNamespace(type="text", text="Calling tool"),
            SimpleNamespace(
                type="tool_use",
                id="toolu_01",
                name="get_weather",
                input={"city": "Chicago"},
            ),
        ],
        stop_reason="tool_use",
    )
    provider, _ = _provider(client)

    request = LLMRequest(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[
            Message(
                role="assistant",
                content=[
                    TextBlock(text="Let me check"),
                    ToolUseBlock(id="prev_01", name="get_time", input={"tz": "UTC"}),
                ],
            ),
            Message(
                role="user",
                content=[
                    ToolResultBlock(tool_use_id="prev_01", content="2026-05-20T15:00:00Z"),
                ],
            ),
        ],
        tools=[
            ToolDef(
                name="get_weather",
                description="Look up the weather for a city",
                input_schema={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            )
        ],
    )

    response = await provider.create_message(request)

    captured_messages = client.messages.captured["messages"]
    assert captured_messages[0]["content"][1] == {
        "type": "tool_use",
        "id": "prev_01",
        "name": "get_time",
        "input": {"tz": "UTC"},
    }
    assert captured_messages[1]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "prev_01",
        "content": "2026-05-20T15:00:00Z",
    }
    captured_tools = client.messages.captured["tools"]
    assert captured_tools[0]["name"] == "get_weather"
    assert captured_tools[0]["input_schema"]["required"] == ["city"]

    assert response.stop_reason == "tool_use"
    assert isinstance(response.content[1], ToolUseBlock)
    assert response.content[1].name == "get_weather"
    assert response.content[1].input == {"city": "Chicago"}


async def test_create_message_omits_optional_fields() -> None:
    client = FakeClient()
    client.messages.response = _fake_response()
    provider, _ = _provider(client)

    await provider.create_message(
        LLMRequest(
            model="claude-haiku-4-5",
            max_tokens=128,
            messages=[Message(role="user", content="hi")],
        )
    )

    assert "system" not in client.messages.captured
    assert "tools" not in client.messages.captured
    assert "temperature" not in client.messages.captured


async def test_tool_result_is_error_flag_propagated() -> None:
    client = FakeClient()
    client.messages.response = _fake_response()
    provider, _ = _provider(client)

    await provider.create_message(
        LLMRequest(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[
                Message(
                    role="user",
                    content=[ToolResultBlock(tool_use_id="t1", content="boom", is_error=True)],
                ),
            ],
        )
    )

    block = client.messages.captured["messages"][0]["content"][0]
    assert block["is_error"] is True


async def test_unknown_sdk_block_type_rejected() -> None:
    client = FakeClient()
    client.messages.response = _fake_response(
        content=[SimpleNamespace(type="image", source={"data": "..."})],
    )
    provider, _ = _provider(client)

    with pytest.raises(ValueError, match="unsupported SDK block type"):
        await provider.create_message(
            LLMRequest(
                model="claude-sonnet-4-6",
                max_tokens=256,
                messages=[Message(role="user", content="x")],
            )
        )


async def test_aclose_closes_client() -> None:
    provider, client = _provider()
    await provider.aclose()
    assert client.closed is True


async def test_cache_usage_passthrough() -> None:
    client = FakeClient()
    client.messages.response = _fake_response(cache_read=1500, cache_creation=400)
    provider, _ = _provider(client)

    response = await provider.create_message(
        LLMRequest(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[Message(role="user", content="x")],
        )
    )

    assert response.usage.cache_read_input_tokens == 1500
    assert response.usage.cache_creation_input_tokens == 400
