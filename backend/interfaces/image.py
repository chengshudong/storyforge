from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class ImageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ImageResult:
    prompt_id: str
    status: ImageStatus
    images: list[bytes] | None = None
    filenames: list[str] | None = None
    error: str | None = None


class ImageProvider(ABC):
    """Interface for image generation backends (ComfyUI, etc.).

    Per OSS_REGISTRY: Provider → Adapter → Interface → Agent → Workflow → API.
    """

    @abstractmethod
    async def generate(self, workflow: dict) -> str:
        """Submit a ComfyUI workflow. Returns prompt_id."""

    @abstractmethod
    async def poll(self, prompt_id: str) -> ImageResult:
        """Check generation status. Returns ImageResult with status + images if done."""

    @abstractmethod
    async def upload_image(self, filename: str, data: bytes) -> str:
        """Upload a reference image to the provider (for InstantID face input)."""

    @abstractmethod
    async def health(self) -> bool:
        """Check provider is reachable and ready."""
