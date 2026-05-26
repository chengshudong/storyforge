from __future__ import annotations

import os
import time

from anthropic import AsyncAnthropic

from interfaces.llm import LLMProvider, ModelResponse


class AnthropicAdapter(LLMProvider):
    """Anthropic Claude adapter. Lazily initializes the client on first call."""

    def __init__(self) -> None:
        self._client: AsyncAnthropic | None = None

    def _ensure_client(self) -> AsyncAnthropic:
        if self._client is not None:
            return self._client
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("anthropic: ANTHROPIC_API_KEY not configured")
        self._client = AsyncAnthropic(api_key=api_key)
        return self._client

    async def generate(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        client = self._ensure_client()
        start = time.time()
        resp = await client.messages.create(
            model=model,
            max_tokens=kwargs.pop("max_tokens", 4096),
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        duration_ms = int((time.time() - start) * 1000)
        return ModelResponse(
            text=resp.content[0].text if resp.content else "",
            model=resp.model,
            provider="anthropic",
            tokens_input=resp.usage.input_tokens if resp.usage else 0,
            tokens_output=resp.usage.output_tokens if resp.usage else 0,
            duration_ms=duration_ms,
        )

    async def stream(self, prompt: str, model: str, **kwargs):
        client = self._ensure_client()
        async with client.messages.stream(
            model=model,
            max_tokens=kwargs.pop("max_tokens", 4096),
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def embedding(self, texts: list[str], model: str) -> list[list[float]]:
        raise NotImplementedError("Anthropic does not support embeddings")

    async def health(self) -> dict:
        if os.getenv("ANTHROPIC_API_KEY", "") == "":
            return {"status": "unconfigured", "error": "no api key"}
        return {"status": "healthy", "latency_ms": 0}
