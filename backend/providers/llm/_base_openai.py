from __future__ import annotations

import os
import time

from openai import AsyncOpenAI

from interfaces.llm import LLMProvider, ModelResponse


class OpenAICompatibleAdapter(LLMProvider):
    """Base adapter for OpenAI-compatible APIs (OpenAI, DeepSeek, OpenRouter).

    Lazily initializes the client on first call — no env var access at import time.
    """

    def __init__(
        self,
        api_key_env: str,
        base_url_env: str | None = None,
        default_base_url: str | None = None,
        provider_name: str = "openai",
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url_env = base_url_env
        self._default_base_url = default_base_url
        self._provider_name = provider_name
        self._client: AsyncOpenAI | None = None

    def _ensure_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        api_key = os.getenv(self._api_key_env, "")
        if not api_key:
            raise RuntimeError(f"{self._provider_name}: {self._api_key_env} not configured")
        base_url = None
        if self._base_url_env:
            base_url = os.getenv(self._base_url_env, "") or self._default_base_url
        elif self._default_base_url:
            base_url = self._default_base_url
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return self._client

    async def generate(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        client = self._ensure_client()
        start = time.time()
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        duration_ms = int((time.time() - start) * 1000)
        choice = resp.choices[0]
        return ModelResponse(
            text=choice.message.content or "",
            model=resp.model,
            provider=self._provider_name,
            tokens_input=resp.usage.prompt_tokens if resp.usage else 0,
            tokens_output=resp.usage.completion_tokens if resp.usage else 0,
            duration_ms=duration_ms,
        )

    async def stream(self, prompt: str, model: str, **kwargs):
        client = self._ensure_client()
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            **kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def embedding(self, texts: list[str], model: str) -> list[list[float]]:
        client = self._ensure_client()
        resp = await client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in resp.data]

    async def health(self) -> dict:
        if os.getenv(self._api_key_env, "") == "":
            return {"status": "unconfigured", "error": "no api key"}
        try:
            client = self._ensure_client()
        except Exception as e:
            return {"status": "unconfigured", "error": str(e)[:200]}
        start = time.time()
        try:
            await client.models.list()
            latency_ms = int((time.time() - start) * 1000)
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200]}
