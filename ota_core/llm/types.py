from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["user", "assistant"]
StopReason = Literal["end_turn", "max_tokens", "tool_use", "stop_sequence", "pause_turn"]


@dataclass(frozen=True)
class TextBlock:
    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


@dataclass(frozen=True)
class ToolResultBlock:
    tool_use_id: str
    content: str
    is_error: bool = False
    type: Literal["tool_result"] = "tool_result"


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True)
class Message:
    role: Role
    content: str | list[ContentBlock]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: list[Message]
    max_tokens: int
    system: str | None = None
    tools: list[ToolDef] | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    model: str
    content: list[ContentBlock]
    usage: Usage
    stop_reason: StopReason


@dataclass(frozen=True)
class ProviderMetadata:
    name: str
    region: str
