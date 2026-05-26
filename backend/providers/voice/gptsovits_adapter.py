from __future__ import annotations

import logging

import httpx

from interfaces.voice import SynthesisRequest, VoiceProvider, VoiceResult, VoiceStatus

logger = logging.getLogger(__name__)

GPTSOVITS_TIMEOUT = 60
GPTSOVITS_CONNECT_TIMEOUT = 10


class GPTSoVITSAdapter(VoiceProvider):
    """GPT-SoVITS HTTP API adapter (optional fallback).

    GPT-SoVITS REST API:
    - POST /set_reference       -> {"speaker_id": "..."}
    - POST /tts                 -> WAV bytes
    - GET  /health              -> {"status": "ok"}
    """

    def __init__(self, base_url: str = "http://localhost:5002") -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=GPTSOVITS_CONNECT_TIMEOUT,
            read=GPTSOVITS_TIMEOUT,
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

        response = await self._request("POST", "/set_reference", files=files, data=data)
        result = response.json()
        speaker = result.get("speaker_id", "")
        logger.info("GPT-SoVITS cloned voice for %s -> speaker %s", character_name, speaker)
        return speaker

    async def synthesize(self, request: SynthesisRequest) -> VoiceResult:
        payload = {
            "text": request.text,
            "speaker": request.speaker,
            "emotion": request.emotion,
            "speed": request.speed,
        }
        try:
            response = await self._request("POST", "/tts", json=payload)
            audio = response.content
            duration_ms = float(len(audio)) / 32000.0 * 1000
            return VoiceResult(
                speaker=request.speaker or "",
                status=VoiceStatus.DONE,
                audio=audio,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error("GPT-SoVITS synthesis failed: %s", e)
            return VoiceResult(
                speaker=request.speaker or "",
                status=VoiceStatus.FAILED,
                error=str(e),
            )

    async def synthesize_batch(self, requests: list[SynthesisRequest]) -> list[VoiceResult]:
        results = []
        for req in requests:
            results.append(await self.synthesize(req))
        return results

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
        return []

    async def delete_speaker(self, speaker: str) -> bool:
        return True
