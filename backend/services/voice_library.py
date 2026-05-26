from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)

SPEAKER_TTL = 604800     # 7 days
SYNTHESIS_TTL = 2592000  # 30 days


class VoiceLibrary:
    """Voice speaker cache and audio cache.

    Two-layer cache:
    L1 (Redis): speaker mappings, synthesis results
    L2 (MinIO): audio files (permanent storage)
    """

    def __init__(self, cache_service) -> None:
        self._cache = cache_service

    # ── Speaker cache ────────────────────────────────────────────────────

    async def get_speaker(self, character_id: str) -> dict | None:
        key = f"voice:speaker:{character_id}"
        return await self._cache.get(key)

    async def set_speaker(self, character_id: str, speaker: str,
                          provider: str, version: int) -> None:
        key = f"voice:speaker:{character_id}"
        await self._cache.set(key, {
            "speaker": speaker,
            "provider": provider,
            "version": version,
        }, ttl=SPEAKER_TTL)

    async def invalidate_speaker(self, character_id: str) -> None:
        key = f"voice:speaker:{character_id}"
        try:
            from infra.redis import get_redis
            client = await get_redis()
            await client.delete(key)
        except Exception as e:
            logger.warning("speaker cache invalidate failed: %s", e)

    # ── Synthesis cache ──────────────────────────────────────────────────

    @staticmethod
    def synthesis_cache_key(speaker: str, text: str, emotion: str,
                            speed: float, pitch: int) -> str:
        raw = f"{speaker}|{text}|{emotion}|{speed}|{pitch}"
        return f"voice:synth:{hashlib.md5(raw.encode()).hexdigest()[:16]}"

    async def get_synthesis(self, speaker: str, text: str, emotion: str,
                            speed: float, pitch: int) -> bytes | None:
        key = self.synthesis_cache_key(speaker, text, emotion, speed, pitch)
        result = await self._cache.get(key)
        if result and "audio_b64" in result:
            import base64
            return base64.b64decode(result["audio_b64"])
        return None

    async def set_synthesis(self, speaker: str, text: str, emotion: str,
                            speed: float, pitch: int, audio: bytes) -> None:
        import base64
        key = self.synthesis_cache_key(speaker, text, emotion, speed, pitch)
        await self._cache.set(key, {
            "speaker": speaker,
            "text": text[:100],
            "emotion": emotion,
            "speed": speed,
            "pitch": pitch,
            "audio_b64": base64.b64encode(audio).decode("ascii"),
        }, ttl=SYNTHESIS_TTL)

    async def invalidate_character_audio(self, character_id: str) -> None:
        """Clear all cached audio for a character on profile update.
        Only removes speaker cache — synthesis cache keys contain speaker IDs
        which change on re-clone, so they naturally expire."""
        await self.invalidate_speaker(character_id)

    # ── Provider health ──────────────────────────────────────────────────

    async def get_active_provider(self) -> str:
        key = "voice:active_provider"
        result = await self._cache.get(key)
        return result.get("provider", "cosyvoice") if result else "cosyvoice"

    async def set_active_provider(self, provider: str) -> None:
        key = "voice:active_provider"
        await self._cache.set(key, {"provider": provider}, ttl=60)
