from __future__ import annotations

import yaml
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.model_router.secret_loader import SecretLoader

router = APIRouter(prefix="/models", tags=["models"])


def _load_registry() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=500, detail="models.yaml not found")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_provider_map() -> dict:
    """Create all provider adapters unconditionally. Each adapter lazily
    initializes its client on first call — no API keys required at startup."""
    from providers.llm.deepseek import DeepSeekAdapter
    from providers.llm.openai import OpenAIAdapter
    from providers.llm.anthropic import AnthropicAdapter
    from providers.llm.gemini import GeminiAdapter
    from providers.llm.openrouter import OpenRouterAdapter
    from providers.llm.local import LocalAdapter

    return {
        "deepseek": DeepSeekAdapter(),
        "openai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
        "gemini": GeminiAdapter(),
        "openrouter": OpenRouterAdapter(),
        "local": LocalAdapter(),
    }


class ModelTaskInfo(BaseModel):
    provider: str
    model: str


class HealthResponse(BaseModel):
    status: str
    providers: dict


class TestRequest(BaseModel):
    task: str = "summary"
    prompt: str
    provider: str | None = None


class TestResponse(BaseModel):
    text: str
    provider: str
    model: str
    tokens_input: int
    tokens_output: int
    duration_ms: int


@router.get("")
async def list_models() -> dict:
    registry = _load_registry()
    return {
        "providers": {
            name: {"models": cfg.get("models", [])}
            for name, cfg in registry.get("providers", {}).items()
        },
        "tasks": registry.get("tasks", {}),
    }


@router.get("/health", response_model=HealthResponse)
async def models_health() -> HealthResponse:
    registry = _load_registry()
    secrets = SecretLoader.validate()

    providers = {}
    for name in registry.get("providers", {}):
        if name == "local":
            providers[name] = {"status": "healthy", "latency_ms": 0}
        elif not secrets.get(f"{name.upper()}_API_KEY", False):
            providers[name] = {"status": "unconfigured"}
        else:
            providers[name] = {"status": "healthy", "latency_ms": 0}

    return HealthResponse(
        status="ok" if any(secrets.values()) else "degraded",
        providers=providers,
    )


@router.post("/test", response_model=TestResponse)
async def test_model(req: TestRequest) -> TestResponse:
    from services.model_router.router import ModelRouter

    registry = _load_registry()
    provider_map = _build_provider_map()

    router_inst = ModelRouter(provider_map, registry)

    try:
        result = await router_inst.generate(
            task=req.task,
            prompt=req.prompt,
            provider_override=req.provider,
        )
        return TestResponse(
            text=result.text,
            provider=result.provider,
            model=result.model,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            duration_ms=result.duration_ms,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
