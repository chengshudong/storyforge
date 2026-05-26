from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from interfaces.video import VideoProvider, VideoResult, VideoStatus, VideoSubmitRequest

logger = logging.getLogger(__name__)

COGVIDEOX_TIMEOUT = 600
COGVIDEOX_CONNECT_TIMEOUT = 10
COGVIDEOX_POLL_INTERVAL = 2.0
COGVIDEOX_POLL_MAX = 150


class CogVideoXAdapter(VideoProvider):
    """CogVideoX I2V REST API adapter (THUDM fallback).

    Key differences from Wan2.1:
    - Uses /generate, /status/{id}, /download/{id} endpoints
    - JSON-only payload (image as base64 data URI)
    - Uses num_inference_steps instead of motion_bucket_id
    - Default guidance_scale 6.0 vs 7.5
    """

    def __init__(self, base_url: str = "http://localhost:7861", timeout: int = COGVIDEOX_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=COGVIDEOX_CONNECT_TIMEOUT,
            read=timeout,
            write=120.0,
            pool=10.0,
        )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def submit(self, request: VideoSubmitRequest) -> str:
        client = await self._get_client()
        image_b64 = ""
        if request.image:
            image_b64 = base64.b64encode(request.image).decode("ascii")

        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "image_base64": image_b64,
            "seed": request.seed,
            "fps": request.fps,
            "num_frames": request.num_frames,
            "guidance_scale": request.guidance_scale if request.guidance_scale else 6.0,
            "num_inference_steps": 50,
            "width": request.width,
            "height": request.height,
        }
        resp = await client.post(f"{self._base_url}/generate", json=payload)
        resp.raise_for_status()
        task_id = resp.json().get("task_id", "")
        logger.info("cogvideox submit: task_id=%s", task_id)
        return task_id

    async def poll(self, prompt_id: str) -> VideoResult:
        client = await self._get_client()
        for i in range(COGVIDEOX_POLL_MAX):
            try:
                resp = await client.get(f"{self._base_url}/status/{prompt_id}")
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "")

                if status == "completed":
                    video_resp = await client.get(f"{self._base_url}/download/{prompt_id}")
                    video_resp.raise_for_status()
                    return VideoResult(
                        prompt_id=prompt_id,
                        status=VideoStatus.DONE,
                        video=video_resp.content,
                        duration_s=data.get("duration", 0),
                    )
                elif status == "failed":
                    return VideoResult(
                        prompt_id=prompt_id,
                        status=VideoStatus.FAILED,
                        error=data.get("error", "Unknown error"),
                    )
            except httpx.HTTPStatusError as e:
                logger.warning("cogvideox poll %d: HTTP %s", i, e.response.status_code)
            except Exception as e:
                logger.warning("cogvideox poll %d error: %s", i, e)

            await asyncio.sleep(COGVIDEOX_POLL_INTERVAL)

        return VideoResult(
            prompt_id=prompt_id,
            status=VideoStatus.FAILED,
            error=f"timeout after {COGVIDEOX_POLL_MAX * COGVIDEOX_POLL_INTERVAL}s",
        )

    async def cancel(self, prompt_id: str) -> bool:
        try:
            client = await self._get_client()
            resp = await client.post(f"{self._base_url}/cancel/{prompt_id}")
            return resp.status_code == 200
        except Exception:
            return False

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self._base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
