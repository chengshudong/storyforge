from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ModelResponse:
    text: str
    model: str
    provider: str
    tokens_input: int = 0
    tokens_output: int = 0
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        """Generate a completion from the given prompt."""

    @abstractmethod
    async def stream(self, prompt: str, model: str, **kwargs):
        """Yield completion chunks as an async generator."""

    @abstractmethod
    async def embedding(self, texts: list[str], model: str) -> list[list[float]]:
        """Generate embeddings for the given texts."""

    @abstractmethod
    async def health(self) -> dict:
        """Return {"status": "healthy"|"unhealthy", "latency_ms": int, "error": str|None}."""
