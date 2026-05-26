from __future__ import annotations

import asyncio
import logging

import httpx

from interfaces.video import VideoProvider, VideoResult, VideoStatus, VideoSubmitRequest

logger = logging.getLogger(__name__)

WAN21_TIMEOUT = 600
WAN21_CONNECT_TIMEOUT = 10
WAN21_POLL_INTERVAL = 2.0
WAN21_POLL_MAX = 150  # 5 min max


class Wan21Adapter(VideoProvider):
    """Wan2.1 I2V REST API adapter.

    Wan2.1 REST API:
    - POST /api/v1/video/submit      -> {"task_id": "..."}
    - GET  /api/v1/video/status/{id} -> {"status": "...", "video_url": "..."}
    - GET  /api/v1/video/download/{id} -> MP4 bytes
    - POST /api/v1/video/cancel/{id} -> {"cancelled": true}
    - GET  /api/health                -> {"status": "ok"}
    """

    def __init__(self, base_url: str = "http://localhost:7860", timeout: int = WAN21_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=WAN21_CONNECT_TIMEOUT,
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
        data = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": str(request.seed),
            "fps": str(request.fps),
            "num_frames": str(request.num_frames),
            "guidance_scale": str(request.guidance_scale),
            "width": str(request.width),
            "height": str(request.height),
            "motion_bucket_id": str(request.motion_bucket_id),
        }
        files = {}
        if request.image:
            filename = request.image_filename or "keyframe.png"
            files["image"] = (filename, request.image, "image/png")

        resp = await client.post(
            f"{self._base_url}/api/v1/video/submit",
            data=data,
            files=files,
        )
        resp.raise_for_status()
        task_id = resp.json().get("task_id", "")
        logger.info("wan21 submit: task_id=%s", task_id)
        return task_id

    async def poll(self, prompt_id: str) -> VideoResult:
        client = await self._get_client()
        for i in range(WAN21_POLL_MAX):
            try:
                resp = await client.get(
                    f"{self._base_url}/api/v1/video/status/{prompt_id}"
                )
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "")

                if status == "completed":
                    video_resp = await client.get(
                        f"{self._base_url}/api/v1/video/download/{prompt_id}"
                    )
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
                logger.warning("wan21 poll %d: HTTP %s", i, e.response.status_code)
            except Exception as e:
                logger.warning("wan21 poll %d error: %s", i, e)

            await asyncio.sleep(WAN21_POLL_INTERVAL)

        return VideoResult(
            prompt_id=prompt_id,
            status=VideoStatus.FAILED,
            error=f"timeout after {WAN21_POLL_MAX * WAN21_POLL_INTERVAL}s",
        )

    async def cancel(self, prompt_id: str) -> bool:
        try:
            client = await self._get_client()
            resp = await client.post(f"{self._base_url}/api/v1/video/cancel/{prompt_id}")
            return resp.status_code == 200
        except Exception:
            return False

    async def health(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self._base_url}/api/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
