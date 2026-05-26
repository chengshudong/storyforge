from __future__ import annotations

import asyncio
import logging

import httpx

from interfaces.voice import SynthesisRequest, VoiceProvider, VoiceResult, VoiceStatus

logger = logging.getLogger(__name__)

COSYVOICE_TIMEOUT = 60
COSYVOICE_CONNECT_TIMEOUT = 10
POLL_INTERVAL = 2
POLL_MAX_ITERATIONS = 30


class CosyVoiceAdapter(VoiceProvider):
    """CosyVoice HTTP API adapter.

    CosyVoice REST API:
    - POST /upload              -> {"voice_id": "..."}
    - POST /tts                 -> WAV bytes
    - GET  /voices              -> ["voice_id", ...]
    - DELETE /voices/{id}      -> {"deleted": true}
    - GET  /health              -> {"status": "ok"}
    """

    def __init__(self, base_url: str = "http://localhost:5001") -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=COSYVOICE_CONNECT_TIMEOUT,
            read=COSYVOICE_TIMEOUT,
            write=30.0,
            pool=10.0,
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, f"{self._base_url}{path}", **kwargs)
            response.raise_for_status()
            return response

    async def clone_voice(self, character_name: str, reference_audio: bytes,
                          reference_text: str | None = None) -> str:
        files = {"audio": (f"{character_name}_ref.wav", reference_audio, "audio/wav")}
        data = {"name": character_name}
        if reference_text:
            data["text"] = reference_text

        response = await self._request("POST", "/upload", files=files, data=data)
        result = response.json()
        speaker = result.get("voice_id", "")
        logger.info("cloned voice for %s -> speaker %s", character_name, speaker)
        return speaker

    async def synthesize(self, request: SynthesisRequest) -> VoiceResult:
        payload = {
            "text": request.text,
            "speaker": request.speaker,
            "emotion": request.emotion,
            "speed": request.speed,
            "pitch": request.pitch,
        }
        if request.emotion_vector:
            payload["emotion_vector"] = request.emotion_vector

        try:
            response = await self._request("POST", "/tts", json=payload)
            audio = response.content
            duration_ms = float(len(audio)) / 32000.0 * 1000  # 16-bit mono 16kHz = 32000 bytes/s
            return VoiceResult(
                speaker=request.speaker or "",
                status=VoiceStatus.DONE,
                audio=audio,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error("synthesis failed for speaker %s: %s", request.speaker, e)
            return VoiceResult(
                speaker=request.speaker or "",
                status=VoiceStatus.FAILED,
                error=str(e),
            )

    async def synthesize_batch(self, requests: list[SynthesisRequest]) -> list[VoiceResult]:
        semaphore = asyncio.Semaphore(3)
        async def _one(req: SynthesisRequest) -> VoiceResult:
            async with semaphore:
                return await self.synthesize(req)
        return list(await asyncio.gather(*[_one(r) for r in requests]))

    async def preview(self, speaker: str, text: str) -> VoiceResult:
        request = SynthesisRequest(
            text=text[:200],
            speaker=speaker,
            emotion="neutral",
            speed=1.0,
        )
        return await self.synthesize(request)

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/health")
            return response.status_code == 200
        except Exception:
            return False

    async def list_speakers(self) -> list[str]:
        try:
            response = await self._request("GET", "/voices")
            return response.json()
        except Exception:
            return []

    async def delete_speaker(self, speaker: str) -> bool:
        try:
            await self._request("DELETE", f"/voices/{speaker}")
            return True
        except Exception:
            return False
