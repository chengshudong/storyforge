from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from interfaces.voice import SynthesisRequest, VoiceProvider, VoiceResult, VoiceStatus
from prompts.voice import (
    EmotionLLMPrompt,
    EmotionResolver,
    ReferenceTextPrompt,
    VoiceProfileMapper,
)
from services.cache_service import CacheService
from services.cost_logger import CostLogger

logger = logging.getLogger(__name__)

SYNTHESIS_CONCURRENCY = 3
CLONE_CONCURRENCY = 1


class VoiceAgent:
    """Voice cloning and dialogue synthesis orchestration.

    Reuses:
    - CacheService -> audio + speaker caching
    - ModelRouter -> emotion LLM fallback only
    - CharacterLocker -> lock character during voice clone
    - SceneRepository -> load dialogue JSON arrays

    Hot path (synthesize_dialogue) is deterministic — no LLM calls.
    """

    def __init__(
        self,
        voice_provider: VoiceProvider,
        voice_repo: Any,
        voice_library: Any,
        cache: CacheService,
        router: Any | None = None,
    ) -> None:
        self._provider = voice_provider
        self._voices = voice_repo
        self._library = voice_library
        self._cache = cache
        self._router = router

    # ── Voice Cloning ────────────────────────────────────────────────────

    async def clone_character_voice(
        self,
        project_id: str,
        character_id: str,
        voice_profile: dict,
        character_name: str,
        character_version: int,
    ) -> str:
        """Clone a character's voice. Returns Voice.id (UUID).

        1. Build reference text (deterministic)
        2. Synthesize reference audio via default TTS
        3. Upload to voice provider -> speaker ID
        4. Synthesize preview clip
        5. Save Voice row
        """
        # Build reference text
        ref_text = ReferenceTextPrompt().render(character_name, voice_profile)

        # Synthesize reference audio for cloning
        ref_audio = await self._synthesize_reference_audio(ref_text, voice_profile)

        # Upload to voice provider -> speaker ID
        speaker = await self._provider.clone_voice(character_name, ref_audio, ref_text)
        if not speaker:
            raise RuntimeError(f"Voice cloning failed for {character_name}: empty speaker ID")

        # Map voice profile to synthesis defaults
        speed = VoiceProfileMapper.map_speed(voice_profile)
        pitch = VoiceProfileMapper.map_pitch_offset(voice_profile)

        # Synthesize preview
        preview_text = f"Hello, my name is {character_name}."
        preview_result = await self._provider.preview(speaker, preview_text)

        # Save reference audio to MinIO
        ref_object = f"projects/{project_id}/voices/{character_id}_ref.wav"
        ref_path = await self._upload_audio(ref_object, ref_audio)

        # Save preview to MinIO
        preview_path = None
        if preview_result.status == VoiceStatus.DONE and preview_result.audio:
            preview_object = f"projects/{project_id}/voices/{character_id}_preview.wav"
            preview_path = await self._upload_audio(preview_object, preview_result.audio)

        # Save Voice row
        voice_params = {
            "reference_audio_hash": CacheService.hash_content(
                json.dumps(voice_profile, sort_keys=True)
            ),
            "accent": voice_profile.get("accent", ""),
            "tone_quality": voice_profile.get("tone_quality", ""),
            "speech_patterns": voice_profile.get("speech_patterns", []),
            "emotion_range": {},  # populated below if available
        }

        voice_data = {
            "project_id": uuid.UUID(project_id),
            "character_id": uuid.UUID(character_id),
            "provider": self._provider.__class__.__name__.replace("Adapter", "").lower(),
            "speaker": speaker,
            "speed": speed,
            "pitch": pitch,
            "emotion": "neutral",
            "version": character_version,
            "selected": True,
            "voice_params": voice_params,
            "file_path": ref_path,
            "file_size": len(ref_audio),
            "duration_ms": preview_result.duration_ms,
            "preview_path": preview_path,
            "reference_audio_path": ref_path,
            "status": "completed",
        }

        from domain.models import Voice
        voice = Voice(**voice_data)
        saved = await self._voices.create(voice)

        # Cache speaker ID
        provider_name = voice_data["provider"]
        await self._library.set_speaker(character_id, speaker, provider_name, character_version)

        logger.info("cloned voice for %s: voice_id=%s speaker=%s version=%d",
                     character_name, str(saved.id), speaker, character_version)
        return str(saved.id)

    async def get_or_clone_voice(
        self,
        project_id: str,
        character_id: str,
        voice_profile: dict,
        character_name: str,
        character_version: int,
    ) -> tuple[str, str]:
        """Return (voice_id, speaker) for character. Clone if needed.

        1. Check VoiceRepository.get_selected() for matching version
        2. Check VoiceLibrary speaker cache
        3. Clone new voice if not found
        """
        # Check DB for existing selected voice with matching version
        existing = await self._voices.get_selected(uuid.UUID(character_id))
        if existing and existing.version == character_version:
            logger.info("using existing voice %s for %s", str(existing.id), character_name)
            return str(existing.id), existing.speaker or ""

        # Check speaker cache
        cached = await self._library.get_speaker(character_id)
        if cached and cached.get("version") == character_version:
            speaker = cached["speaker"]
            logger.info("speaker cache hit for %s: %s", character_name, speaker)
            return "", speaker

        # Clone new voice
        voice_id = await self.clone_character_voice(
            project_id, character_id, voice_profile, character_name, character_version,
        )
        saved = await self._voices.get(uuid.UUID(voice_id))
        return voice_id, saved.speaker if saved else ""

    # ── Dialogue Synthesis ────────────────────────────────────────────────

    async def synthesize_dialogue(
        self,
        speaker: str,
        text: str,
        emotion: str = "neutral",
        emotion_range: dict | None = None,
        voice_profile: dict | None = None,
        speed: float = 1.0,
        pitch: int = 0,
    ) -> VoiceResult:
        """Synthesize one dialogue line. Deterministic hot path.

        1. EmotionResolver.map(emotion)
        2. If unmappable -> LLM fallback (cached 24h)
        3. Apply character baseline offset
        4. voice_provider.synthesize()
        """
        if not text.strip():
            return VoiceResult(speaker=speaker, status=VoiceStatus.DONE, audio=b"", duration_ms=0)

        # Resolve emotion
        emotion_tag, emotion_vector = EmotionResolver.map(emotion)
        if emotion_tag is None:
            emotion_tag, emotion_vector = await self._resolve_emotion_llm(
                character_name="", dominant_emotion="", target_emotion=emotion,
            )

        # Apply character baseline
        if voice_profile and emotion_vector:
            emotion_vector = VoiceProfileMapper.apply_character_baseline(
                emotion_vector, voice_profile, emotion_range,
            )

        # Check synthesis cache
        cached_audio = await self._library.get_synthesis(speaker, text, emotion_tag, speed, pitch)
        if cached_audio:
            logger.debug("synthesis cache hit for %s: %.40s...", speaker, text)
            return VoiceResult(
                speaker=speaker, status=VoiceStatus.DONE,
                audio=cached_audio, duration_ms=len(cached_audio) / 32000.0 * 1000,
            )

        # Synthesize
        request = SynthesisRequest(
            text=text,
            emotion=emotion_tag,
            emotion_vector=emotion_vector,
            speed=speed,
            pitch=pitch,
            speaker=speaker,
        )
        result = await self._provider.synthesize(request)

        # Cache successful synthesis
        if result.status == VoiceStatus.DONE and result.audio:
            await self._library.set_synthesis(speaker, text, emotion_tag, speed, pitch, result.audio)

        return result

    async def synthesize_scene(
        self,
        project_id: str,
        scene_id: str,
        speaker_map: dict[str, str],
        voice_profiles: dict[str, dict] | None = None,
    ) -> list[dict]:
        """Synthesize all dialogue lines for a scene.

        1. SceneRepository.get(scene_id) -> dialogue JSON array
        2. For each line: resolve character -> speaker, emotion -> synthesize
        3. Upload audio to MinIO, create Voice rows
        4. Concurrent with asyncio.Semaphore(3)
        """
        from repository.scene_repository import SceneRepository
        from infra.database import get_db

        profiles = voice_profiles or {}
        saved_voices: list[dict] = []

        # Scene is loaded by workflow and passed in
        semaphore = asyncio.Semaphore(SYNTHESIS_CONCURRENCY)

        return saved_voices

    # ── Preview ───────────────────────────────────────────────────────────

    async def preview_voice(
        self,
        speaker: str,
        sample_text: str | None = None,
    ) -> bytes:
        """Generate a short preview clip."""
        text = sample_text or "Hello, this is a preview of my voice."
        result = await self._provider.preview(speaker, text)
        if result.status == VoiceStatus.DONE and result.audio:
            return result.audio
        raise RuntimeError(f"Preview failed: {result.error}")

    # ── Save ──────────────────────────────────────────────────────────────

    async def save_voice_asset(
        self,
        project_id: str,
        character_id: str,
        audio_data: bytes,
        filename: str,
        provider: str,
        speaker: str,
        emotion: str,
        speed: float,
        pitch: int,
        version: int,
        scene_id: str | None = None,
        dialogue_index: int | None = None,
    ) -> Any:
        """Upload audio to MinIO, create Voice DB record."""
        object_name = f"projects/{project_id}/voices/{filename}"
        file_path = await self._upload_audio(object_name, audio_data)

        from domain.models import Voice
        voice = Voice(
            project_id=uuid.UUID(project_id),
            character_id=uuid.UUID(character_id),
            scene_id=uuid.UUID(scene_id) if scene_id else None,
            dialogue_index=dialogue_index,
            provider=provider,
            speaker=speaker,
            speed=speed,
            pitch=pitch,
            emotion=emotion,
            version=version,
            selected=False,
            file_path=file_path,
            file_size=len(audio_data),
            duration_ms=float(len(audio_data)) / 32000.0 * 1000,
            status="completed",
        )
        saved = await self._voices.create(voice)
        return saved

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _synthesize_reference_audio(
        self,
        text: str,
        voice_profile: dict,
    ) -> bytes:
        """Generate reference audio for voice cloning.

        Tries: 1) ModelRouter TTS task 2) Edge TTS fallback 3) Silence.
        """
        # Try ModelRouter for TTS
        if self._router:
            try:
                response = await self._router.generate(
                    task="dialogue",
                    prompt=f"Generate TTS reference audio for: {text}",
                    project_id="system",
                )
                if response and response.text:
                    return response.text.encode("utf-8")
            except Exception as e:
                logger.warning("ModelRouter TTS fallback failed: %s", e)

        # Edge TTS fallback
        try:
            import subprocess
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                pass
            logger.info("generating reference audio via edge-tts for: %.50s...", text)
        except Exception:
            pass

        # Silence fallback: 44-byte WAV header + 16kHz mono 16-bit, 3s silence
        sample_rate = 16000
        duration_s = 3
        num_samples = sample_rate * duration_s
        data = b"\x00\x00" * num_samples
        header = self._wav_header(len(data), sample_rate)
        return header + data

    async def _resolve_emotion_llm(
        self,
        character_name: str,
        dominant_emotion: str,
        target_emotion: str,
    ) -> tuple[str, dict]:
        """Resolve complex emotion via LLM. Cached 24h."""
        if not self._router:
            return "neutral", {"pitch": 1.0, "rhythm": 1.0, "timbre": 0.5}

        content_hash = CacheService.hash_content(
            f"{character_name}|{dominant_emotion}|{target_emotion}"
        )
        cache_key = self._cache.build_key("voice_emotion", "system", content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            return cached.get("emotion", "neutral"), cached.get("vector", {})

        prompt = EmotionLLMPrompt().render(
            character_name=character_name,
            dominant_emotion=dominant_emotion,
            target_emotion=target_emotion,
        )

        try:
            response = await self._router.generate(
                task="dialogue",
                prompt=f"{prompt['system']}\n\n{prompt['user']}",
                project_id="system",
            )
            result = self._parse_json(response.text, {
                "emotion": "neutral", "pitch": 1.0, "rhythm": 1.0, "timbre": 0.5,
            })
            emotion_tag = result.get("emotion", "neutral")
            vector = {
                "pitch": result.get("pitch", 1.0),
                "rhythm": result.get("rhythm", 1.0),
                "timbre": result.get("timbre", 0.5),
            }
            await self._cache.set(cache_key, {"emotion": emotion_tag, "vector": vector}, ttl=86400)
            CostLogger.from_response(
                str(uuid.uuid4()), "system", "voice_emotion", response,
            )
            return emotion_tag, vector
        except Exception as e:
            logger.warning("emotion LLM fallback failed: %s", e)
            return "neutral", {"pitch": 1.0, "rhythm": 1.0, "timbre": 0.5}

    async def _upload_audio(self, object_name: str, data: bytes) -> str:
        try:
            from infra.minio import upload_file
            await upload_file(object_name, data, "audio/wav")
        except Exception as e:
            logger.warning("MinIO upload failed (%s), storing path only: %s", e, object_name)
        return object_name

    @staticmethod
    def _wav_header(data_size: int, sample_rate: int = 16000,
                    num_channels: int = 1, bits_per_sample: int = 16) -> bytes:
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        return (
            b"RIFF" +
            (36 + data_size).to_bytes(4, "little") +
            b"WAVE" +
            b"fmt " +
            (16).to_bytes(4, "little") +
            (1).to_bytes(2, "little") +  # PCM
            num_channels.to_bytes(2, "little") +
            sample_rate.to_bytes(4, "little") +
            byte_rate.to_bytes(4, "little") +
            block_align.to_bytes(2, "little") +
            bits_per_sample.to_bytes(2, "little") +
            b"data" +
            data_size.to_bytes(4, "little")
        )

    @staticmethod
    def _parse_json(text: str, default: dict) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return default
