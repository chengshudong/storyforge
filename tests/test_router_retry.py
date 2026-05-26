import asyncio

import pytest

from services.model_router.router import ModelRouter
from interfaces.llm import LLMProvider, ModelResponse


class CountingAdapter(LLMProvider):
    def __init__(self, name: str, fail_count: int = 0, status_code: int | None = None):
        self.name = name
        self.fail_count = fail_count
        self.status_code = status_code
        self.calls = 0

    async def generate(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        self.calls += 1
        if self.fail_count > 0 and self.calls <= self.fail_count:
            e = Exception(f"{self.name} mock error")
            if self.status_code:
                e.status_code = self.status_code
            raise e
        return ModelResponse(
            text="ok", model=model, provider=self.name,
            tokens_input=1, tokens_output=1, duration_ms=1,
        )

    async def stream(self, prompt, model, **kwargs):
        yield ""

    async def embedding(self, texts, model):
        return [[0.1] * 384 for _ in texts]

    async def health(self):
        return {"status": "healthy"}


@pytest.fixture
def registry():
    return {
        "tasks": {"test": {"provider": "a", "model": "model-a"}},
        "fallback": ["a", "b", "local"],
        "degrade": {"test": {"provider": "local", "model": "local-model"}},
    }


def test_fallback_after_first_provider_fails(registry):
    """Router retries same provider 3 times, then falls back to next."""
    a = CountingAdapter("a", fail_count=5)
    b = CountingAdapter("b", fail_count=0)
    local = CountingAdapter("local", fail_count=0)
    router = ModelRouter({"a": a, "b": b, "local": local}, registry)
    result = asyncio.run(router.generate("test", "hello"))
    assert result.provider == "b"
    assert a.calls == 3  # 3 retries on a before fallback to b


def test_non_retryable_error_falls_back(registry):
    """401 is non-retryable — falls back immediately, no retries on same provider."""
    a = CountingAdapter("a", fail_count=1, status_code=401)
    b = CountingAdapter("b", fail_count=0)
    local = CountingAdapter("local", fail_count=0)
    router = ModelRouter({"a": a, "b": b, "local": local}, registry)
    result = asyncio.run(router.generate("test", "hello"))
    assert result.provider == "b"
    assert a.calls == 1


def test_retryable_error_retries_same_provider(registry):
    """500 is retryable — same provider retried up to 3 times before fallback."""
    a = CountingAdapter("a", fail_count=2, status_code=500)
    b = CountingAdapter("b", fail_count=5)
    local = CountingAdapter("local", fail_count=0)
    router = ModelRouter({"a": a, "b": b, "local": local}, registry)
    result = asyncio.run(router.generate("test", "hello"))
    assert result.provider == "a"
    assert a.calls == 3  # 2 failures + 1 success


def test_all_exhausted_degraded_to_local(registry):
    """When all providers in chain fail, degrade to local."""
    a = CountingAdapter("a", fail_count=5, status_code=500)
    b = CountingAdapter("b", fail_count=5, status_code=500)
    local = CountingAdapter("local", fail_count=0)
    router = ModelRouter({"a": a, "b": b, "local": local}, registry)
    result = asyncio.run(router.generate("test", "hello"))
    assert result.provider == "local"


def test_network_error_triggers_fallback(registry):
    """Network errors (no status code) are retryable and trigger fallback."""
    a = CountingAdapter("a", fail_count=5)  # No status_code = network error
    b = CountingAdapter("b", fail_count=0)
    local = CountingAdapter("local", fail_count=0)
    router = ModelRouter({"a": a, "b": b, "local": local}, registry)
    result = asyncio.run(router.generate("test", "hello"))
    assert result.provider == "b"
