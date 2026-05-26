from __future__ import annotations

import os
import time

from google.genai import Client

from interfaces.llm import LLMProvider, ModelResponse


class GeminiAdapter(LLMProvider):
    """Google Gemini adapter. Lazily initializes the client on first call."""

    def __init__(self) -> None:
        self._client: Client | None = None

    def _ensure_client(self) -> Client:
        if self._client is not None:
            return self._client
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("gemini: GEMINI_API_KEY not configured")
        self._client = Client(api_key=api_key)
        return self._client

    async def generate(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        client = self._ensure_client()
        start = time.time()
        resp = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
        )
        duration_ms = int((time.time() - start) * 1000)
        text = resp.text if resp.text else ""
        usage = resp.usage_metadata
        return ModelResponse(
            text=text,
            model=model,
            provider="gemini",
            tokens_input=usage.prompt_token_count if usage else 0,
            tokens_output=usage.candidates_token_count if usage else 0,
            duration_ms=duration_ms,
        )

    async def stream(self, prompt: str, model: str, **kwargs):
        client = self._ensure_client()
        async for chunk in await client.aio.models.generate_content_stream(
            model=model,
            contents=prompt,
        ):
            if chunk.text:
                yield chunk.text

    async def embedding(self, texts: list[str], model: str) -> list[list[float]]:
        client = self._ensure_client()
        embeddings = []
        for text in texts:
            resp = await client.aio.models.embed_content(
                model=model or "text-embedding-004",
                contents=text,
            )
            embeddings.append(resp.embeddings[0].values if resp.embeddings else [])
        return embeddings

    async def health(self) -> dict:
        if os.getenv("GEMINI_API_KEY", "") == "":
            return {"status": "unconfigured", "error": "no api key"}
        return {"status": "healthy", "latency_ms": 0}
