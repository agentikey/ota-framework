from __future__ import annotations

from typing import Any, cast

from anthropic import AsyncAnthropic

from ota_core.llm.types import (
    ContentBlock,
    LLMRequest,
    LLMResponse,
    Message,
    ProviderMetadata,
    StopReason,
    TextBlock,
    ToolDef,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
)

_SUPPORTED_FLAGS: frozenset[str] = frozenset(
    {
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
    }
)

_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "claude-opus-4-7": 200_000,
    "claude-opus-4-7[1m]": 1_000_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}

_DEFAULT_CONTEXT_LIMIT = 200_000


def _message_to_sdk(msg: Message) -> dict[str, Any]:
    if isinstance(msg.content, str):
        return {"role": msg.role, "content": msg.content}
    return {
        "role": msg.role,
        "content": [_block_to_sdk(b) for b in msg.content],
    }


def _block_to_sdk(block: ContentBlock) -> dict[str, Any]:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block.tool_use_id,
        "content": block.content,
    }
    if block.is_error:
        result["is_error"] = True
    return result


def _tool_to_sdk(tool: ToolDef) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _block_from_sdk(block: Any) -> ContentBlock:
    block_type = _attr(block, "type")
    if block_type == "text":
        return TextBlock(text=_attr(block, "text", ""))
    if block_type == "tool_use":
        return ToolUseBlock(
            id=_attr(block, "id"),
            name=_attr(block, "name"),
            input=dict(_attr(block, "input", {})),
        )
    if block_type == "tool_result":
        raw_content = _attr(block, "content", "")
        return ToolResultBlock(
            tool_use_id=_attr(block, "tool_use_id"),
            content=raw_content if isinstance(raw_content, str) else str(raw_content),
            is_error=bool(_attr(block, "is_error", False)),
        )
    raise ValueError(f"unsupported SDK block type: {block_type!r}")


class AnthropicProvider:
    def __init__(self, *, client: AsyncAnthropic, region: str = "us") -> None:
        self._client = client
        self._region = region

    @classmethod
    def from_api_key(cls, api_key: str, *, region: str = "us") -> AnthropicProvider:
        return cls(client=AsyncAnthropic(api_key=api_key), region=region)

    def supports(self, flag: str) -> bool:
        return flag in _SUPPORTED_FLAGS

    def max_context_tokens(self, model: str) -> int:
        return _MODEL_CONTEXT_LIMITS.get(model, _DEFAULT_CONTEXT_LIMIT)

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(name="anthropic_direct", region=self._region)

    async def create_message(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [_message_to_sdk(m) for m in request.messages],
        }
        if request.system is not None:
            kwargs["system"] = request.system
        if request.tools is not None:
            kwargs["tools"] = [_tool_to_sdk(t) for t in request.tools]
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        sdk_response = await self._client.messages.create(**kwargs)

        content = [_block_from_sdk(b) for b in sdk_response.content]
        usage = Usage(
            input_tokens=sdk_response.usage.input_tokens,
            output_tokens=sdk_response.usage.output_tokens,
            cache_read_input_tokens=int(
                _attr(sdk_response.usage, "cache_read_input_tokens", 0) or 0
            ),
            cache_creation_input_tokens=int(
                _attr(sdk_response.usage, "cache_creation_input_tokens", 0) or 0
            ),
        )
        return LLMResponse(
            model=sdk_response.model,
            content=content,
            usage=usage,
            stop_reason=cast(StopReason, sdk_response.stop_reason),
        )

    async def aclose(self) -> None:
        await self._client.close()
