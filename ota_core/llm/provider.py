from __future__ import annotations

from typing import Protocol

from ota_core.llm.types import LLMRequest, LLMResponse, ProviderMetadata


class LLMProvider(Protocol):
    def supports(self, flag: str) -> bool: ...

    def max_context_tokens(self, model: str) -> int: ...

    def metadata(self) -> ProviderMetadata: ...

    async def create_message(self, request: LLMRequest) -> LLMResponse: ...

    async def aclose(self) -> None: ...
