import os
import asyncio

import pytest

from providers.llm.local import LocalAdapter
from providers.llm.openai import OpenAIAdapter
from providers.llm.deepseek import DeepSeekAdapter
from providers.llm.anthropic import AnthropicAdapter
from providers.llm.gemini import GeminiAdapter
from providers.llm.openrouter import OpenRouterAdapter


def test_openai_adapter_unconfigured():
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    adapter = OpenAIAdapter()
    result = asyncio.run(adapter.health())
    assert result["status"] == "unconfigured"


def test_deepseek_adapter_unconfigured():
    if "DEEPSEEK_API_KEY" in os.environ:
        del os.environ["DEEPSEEK_API_KEY"]
    adapter = DeepSeekAdapter()
    result = asyncio.run(adapter.health())
    assert result["status"] == "unconfigured"


def test_anthropic_adapter_unconfigured():
    if "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]
    adapter = AnthropicAdapter()
    result = asyncio.run(adapter.health())
    assert result["status"] == "unconfigured"


def test_gemini_adapter_unconfigured():
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]
    adapter = GeminiAdapter()
    result = asyncio.run(adapter.health())
    assert result["status"] == "unconfigured"


def test_openrouter_adapter_unconfigured():
    if "OPENROUTER_API_KEY" in os.environ:
        del os.environ["OPENROUTER_API_KEY"]
    adapter = OpenRouterAdapter()
    result = asyncio.run(adapter.health())
    assert result["status"] == "unconfigured"


def test_local_adapter_healthy():
    adapter = LocalAdapter()
    import asyncio
    result = asyncio.run(adapter.health())
    assert result["status"] == "healthy"


def test_local_adapter_generate_returns_degraded():
    adapter = LocalAdapter()
    result = asyncio.run(adapter.generate("test", "all-MiniLM-L6-v2"))
    assert result.provider == "local"
    assert result.metadata.get("degraded") is True


def test_local_adapter_embedding():
    adapter = LocalAdapter()
    embeddings = asyncio.run(adapter.embedding(["hello world"], "all-MiniLM-L6-v2"))
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 384


def test_local_adapter_stream_empty():
    adapter = LocalAdapter()

    async def collect():
        chunks = []
        async for chunk in adapter.stream("test", "model"):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())
    assert len(chunks) == 1
    assert chunks[0] == ""
