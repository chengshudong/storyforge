from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class VoiceStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class VoiceResult:
    speaker: str
    status: VoiceStatus
    audio: bytes | None = None
    duration_ms: float | None = None
    error: str | None = None


@dataclass
class SynthesisRequest:
    text: str
    emotion: str = "neutral"
    emotion_vector: dict | None = None
    speed: float = 1.0
    pitch: int = 0
    speaker: str | None = None


class VoiceProvider(ABC):
    """Interface for TTS/voice cloning backends (CosyVoice, GPT-SoVITS).

    Per OSS_REGISTRY: Provider -> Adapter -> Interface -> Agent -> Workflow -> API.
    """

    @abstractmethod
    async def clone_voice(self, character_name: str, reference_audio: bytes,
                          reference_text: str | None = None) -> str:
        """Upload reference audio, create voice clone. Returns provider-side speaker ID."""

    @abstractmethod
    async def synthesize(self, request: SynthesisRequest) -> VoiceResult:
        """Generate TTS audio from text with emotion control."""

    @abstractmethod
    async def synthesize_batch(self, requests: list[SynthesisRequest]) -> list[VoiceResult]:
        """Generate TTS for multiple lines concurrently."""

    @abstractmethod
    async def preview(self, speaker: str, text: str) -> VoiceResult:
        """Quick preview synthesis."""

    @abstractmethod
    async def health(self) -> bool:
        """Check provider is reachable and ready."""

    @abstractmethod
    async def list_speakers(self) -> list[str]:
        """List available speaker IDs on the provider."""

    @abstractmethod
    async def delete_speaker(self, speaker: str) -> bool:
        """Remove a cloned voice from the provider."""
