from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

from interfaces.llm import LLMProvider, ModelResponse
from services.model_router.secret_loader import SecretLoader

logger = logging.getLogger(__name__)

# Per-task read timeouts per MODEL_POLICY §3
TASK_TIMEOUTS: dict[str, int] = {
    "summary": 120,
    "episode": 90,
    "scene": 60,
    "character": 60,
    "dialogue": 60,
    "narration": 60,
    "embedding": 30,
}

# Retry config per MODEL_POLICY §4
RETRY_MAX = 3
BACKOFF_INITIAL = 1.0
BACKOFF_MULTIPLIER = 2.0
BACKOFF_MAX = 30.0


@dataclass
class RouteState:
    task: str
    attempts: list[dict] = field(default_factory=list)
    current_provider: str = ""
    current_model: str = ""
    degraded: bool = False


class ModelRouter:
    """Routes model calls to the appropriate provider with fallback and retry."""

    RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

    def __init__(self, providers: dict[str, LLMProvider], model_registry: dict) -> None:
        self._providers = providers
        self._registry = model_registry
        self._unhealthy: dict[str, float] = {}  # provider -> unhealthy_until timestamp

    def select(self, task: str, provider_override: str | None = None) -> tuple[str, str]:
        task_cfg = self._registry.get("tasks", {}).get(task, {})
        provider = provider_override or task_cfg.get("provider", "local")
        model = task_cfg.get("model", "default")
        return provider, model

    def fallback(self, task: str, failed_provider: str) -> tuple[str, str]:
        fallback_chain = self._registry.get("fallback", [
            "deepseek", "openai", "anthropic", "gemini", "openrouter", "local",
        ])
        idx = fallback_chain.index(failed_provider) if failed_provider in fallback_chain else -1
        now = time.time()

        for i in range(idx + 1, len(fallback_chain)):
            next_provider = fallback_chain[i]
            if next_provider == failed_provider:
                continue
            # Check health
            unhealthy_until = self._unhealthy.get(next_provider, 0)
            if now < unhealthy_until:
                continue
            if next_provider not in self._providers:
                continue
            task_cfg = self._registry.get("tasks", {}).get(task, {})
            model = task_cfg.get("model", "default")
            return next_provider, model

        return "local", "default"

    def degrade(self, task: str) -> tuple[str, str]:
        degrade_map = self._registry.get("degrade", {}).get(task, {})
        provider = degrade_map.get("provider", "local")
        model = degrade_map.get("model", "default")
        logger.warning("degrading task=%s to provider=%s model=%s", task, provider, model)
        return provider, model

    def mark_unhealthy(self, provider: str, duration_s: int = 60) -> None:
        self._unhealthy[provider] = time.time() + duration_s

    def is_healthy(self, provider: str) -> bool:
        unhealthy_until = self._unhealthy.get(provider, 0)
        return time.time() >= unhealthy_until

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        delay = min(BACKOFF_INITIAL * (BACKOFF_MULTIPLIER ** attempt), BACKOFF_MAX)
        jitter = random.uniform(0, delay * 0.1)
        return delay + jitter

    async def generate(self, task: str, prompt: str, project_id: str = "",
                       provider_override: str | None = None, **kwargs) -> ModelResponse:
        timeout = kwargs.pop("_timeout", TASK_TIMEOUTS.get(task, 60))
        state = RouteState(task=task)
        provider_name, model = self.select(task, provider_override)
        state.current_provider = provider_name
        state.current_model = model

        last_error: Exception | None = None

        while True:
            adapter = self._providers.get(provider_name)
            if adapter is None:
                provider_name, model = self.fallback(task, provider_name)
                state.current_provider = provider_name
                state.current_model = model
                continue

            for attempt in range(RETRY_MAX):
                try:
                    result = await asyncio.wait_for(
                        adapter.generate(prompt, model, **kwargs),
                        timeout=timeout,
                    )
                    state.attempts.append({"provider": provider_name, "model": model, "status": "ok"})
                    return result
                except asyncio.TimeoutError:
                    last_error = TimeoutError(f"{provider_name} timed out after {timeout}s")
                    state.attempts.append({
                        "provider": provider_name, "model": model,
                        "status": "timeout", "error": str(last_error)[:200],
                    })
                    delay = self._backoff_delay(attempt)
                    logger.warning("timeout on %s attempt %d, sleeping %.1fs", provider_name, attempt + 1, delay)
                    await asyncio.sleep(delay)
                except Exception as e:
                    last_error = e
                    status_code = getattr(e, "status_code", None)
                    state.attempts.append({
                        "provider": provider_name, "model": model,
                        "status": "error", "error": str(e)[:200],
                    })
                    if status_code and status_code not in self.RETRYABLE_STATUSES:
                        break  # non-retryable — fallback to next provider
                    delay = self._backoff_delay(attempt)
                    logger.warning("retryable error on %s attempt %d: %s, sleeping %.1fs",
                                   provider_name, attempt + 1, str(e)[:100], delay)
                    await asyncio.sleep(delay)

            # Exhausted retries on this provider — fallback
            next_provider, next_model = self.fallback(task, provider_name)
            if next_provider == provider_name or next_provider == "local":
                break
            logger.warning("falling back from %s to %s for task=%s", provider_name, next_provider, task)
            provider_name, model = next_provider, next_model
            state.current_provider = provider_name
            state.current_model = model

        # All attempts failed — degrade
        provider_name, model = self.degrade(task)
        state.degraded = True
        state.current_provider = provider_name
        state.current_model = model

        adapter = self._providers.get(provider_name)
        if adapter is not None:
            logger.warning("degrading to %s for task=%s", provider_name, task)
            try:
                return await asyncio.wait_for(
                    adapter.generate(prompt, model, **kwargs),
                    timeout=timeout,
                )
            except Exception as e:
                last_error = e

        raise RuntimeError(f"All providers exhausted for task={task}: {last_error}")
