import time

import pytest

from services.model_router.router import ModelRouter, RouteState


class StubAdapter:
    async def generate(self, prompt, model, **kwargs): ...
    async def stream(self, prompt, model, **kwargs): yield ""
    async def embedding(self, texts, model): return []
    async def health(self): return {"status": "healthy"}


@pytest.fixture
def registry():
    return {
        "tasks": {
            "summary": {"provider": "deepseek", "model": "deepseek-chat"},
            "embedding": {"provider": "local", "model": "all-MiniLM-L6-v2"},
        },
        "fallback": ["deepseek", "openai", "local"],
        "degrade": {
            "summary": {"provider": "local", "model": "local-model"},
        },
    }


@pytest.fixture
def router(registry):
    stub = StubAdapter()
    return ModelRouter(
        {"deepseek": stub, "openai": stub, "local": stub},
        registry,
    )


def test_select_returns_default_provider(router):
    provider, model = router.select("summary")
    assert provider == "deepseek"
    assert model == "deepseek-chat"


def test_select_with_override(router):
    provider, model = router.select("summary", provider_override="openai")
    assert provider == "openai"


def test_fallback_skips_failed_provider(router):
    provider, model = router.fallback("summary", "deepseek")
    assert provider == "openai"
    assert model == "deepseek-chat"


def test_fallback_last_in_chain_goes_to_local(router):
    provider, model = router.fallback("summary", "openai")
    assert provider == "local"
    assert model == "deepseek-chat"


def test_fallback_skips_unhealthy(router):
    router.mark_unhealthy("openai", duration_s=60)
    provider, model = router.fallback("summary", "deepseek")
    assert provider == "local"


def test_degrade_returns_local(router):
    provider, model = router.degrade("summary")
    assert provider == "local"
    assert model == "local-model"


def test_mark_unhealthy_sticks(router):
    router.mark_unhealthy("deepseek", duration_s=60)
    assert not router.is_healthy("deepseek")


def test_mark_unhealthy_expires(router):
    router.mark_unhealthy("deepseek", duration_s=0)
    time.sleep(0.1)
    assert router.is_healthy("deepseek")


def test_route_state_defaults():
    state = RouteState(task="summary")
    assert state.task == "summary"
    assert state.current_provider == ""
    assert not state.degraded
