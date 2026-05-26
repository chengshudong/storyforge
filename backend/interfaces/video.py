from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class VideoStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class VideoSubmitRequest:
    prompt: str
    negative_prompt: str = ""
    seed: int = 0
    fps: int = 24
    num_frames: int = 120
    guidance_scale: float = 7.5
    width: int = 768
    height: int = 1152
    image: bytes | None = None
    image_filename: str | None = None
    motion_bucket_id: int = 127
    extra_params: dict = field(default_factory=dict)


@dataclass
class VideoResult:
    prompt_id: str
    status: VideoStatus
    video: bytes | None = None
    duration_s: float | None = None
    error: str | None = None


class VideoProvider(ABC):

    @abstractmethod
    async def submit(self, request: VideoSubmitRequest) -> str:
        """Submit a video generation job. Returns prompt_id/task_id."""

    @abstractmethod
    async def poll(self, prompt_id: str) -> VideoResult:
        """Check generation status. Returns VideoResult with video bytes if done."""

    @abstractmethod
    async def cancel(self, prompt_id: str) -> bool:
        """Cancel an in-progress generation."""

    @abstractmethod
    async def health(self) -> bool:
        """Check provider is reachable and ready."""
