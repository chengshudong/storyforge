from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from interfaces.video import VideoProvider, VideoResult, VideoStatus, VideoSubmitRequest
from prompts.video import SceneContextPrompt, SceneVideoPrompt
from services.cache_service import CacheService
from services.video_renderer import SceneRenderer

logger = logging.getLogger(__name__)

VIDEO_CACHE_TTL = 2592000   # 30 days
PROMPT_CACHE_TTL = 604800   # 7 days


class VideoAgent:
    """Orchestrates video generation from scene + character + voice data.

    Follows the same DI pattern as ImageAgent and VoiceAgent:
    - Provider (VideoProvider) for actual generation
    - Repos (VideoRepository, AssetRepository) for data access
    - CacheService for generation caching
    - SceneRenderer for deterministic payload construction
    - ModelRouter for optional LLM prompt enhancement

    Hot path (generate_scene_video) is deterministic — no LLM calls.
    """

    def __init__(
        self,
        video_provider: VideoProvider,
        video_repo: Any,
        asset_repo: Any,
        cache: CacheService,
        router: Any | None = None,
    ) -> None:
        self._provider = video_provider
        self._videos = video_repo
        self._assets = asset_repo
        self._cache = cache
        self._router = router

    # ── Core Generation ────────────────────────────────────────────────

    async def submit_scene_video(
        self,
        project_id: uuid.UUID,
        scene_id: uuid.UUID,
        character_name: str,
        character_profile: dict,
        character_image_data: bytes,
        storyboard: dict,
        seed: int,
        params: "VideoGenerationParams | None" = None,
    ) -> str:
        scene = {"id": str(scene_id)}
        request = SceneRenderer.build_payload(
            scene=scene,
            storyboard=storyboard,
            character_image=character_image_data,
            character_name=character_name,
            character_profile=character_profile,
            seed=seed,
            cfg=params.guidance_scale if params else 7.5,
            width=params.width if params else 768,
            height=params.height if params else 1152,
        )
        return await self._provider.submit(request)

    async def poll_scene_video(self, prompt_id: str) -> VideoResult:
        return await self._provider.poll(prompt_id)

    async def generate_scene_video(
        self,
        project_id: uuid.UUID,
        scene_id: uuid.UUID,
        character_name: str,
        character_profile: dict,
        character_image_data: bytes,
        storyboard: dict,
        seed: int,
        params: "VideoGenerationParams | None" = None,
    ) -> VideoResult:
        prompt_id = await self.submit_scene_video(
            project_id, scene_id, character_name, character_profile,
            character_image_data, storyboard, seed, params,
        )
        return await self._provider.poll(prompt_id)

    # ── Post-Processing ────────────────────────────────────────────────

    async def composite_audio(
        self,
        video_data: bytes,
        audio_data: bytes,
        output_filename: str | None = None,
    ) -> bytes:
        """Add dialogue audio to generated video via ffmpeg."""
        import subprocess
        import tempfile
        import os

        vf = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        af = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        of = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        try:
            vf.write(video_data)
            vf.flush()
            af.write(audio_data)
            af.flush()
            of.close()

            cmd = [
                "ffmpeg", "-y",
                "-i", vf.name,
                "-i", af.name,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                "-loglevel", "error",
                of.name,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode != 0:
                error_msg = stderr.decode()[:200] if stderr else "unknown ffmpeg error"
                raise RuntimeError(f"ffmpeg failed: {error_msg}")

            with open(of.name, "rb") as f:
                return f.read()
        finally:
            for tmp in [vf, af, of]:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    async def extract_thumbnail(
        self,
        video_data: bytes,
        at_seconds: float = 1.5,
    ) -> bytes:
        import subprocess
        import tempfile
        import os

        vf = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        of = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        try:
            vf.write(video_data)
            vf.flush()
            of.close()

            cmd = [
                "ffmpeg", "-y",
                "-i", vf.name,
                "-ss", f"{at_seconds:.3f}",
                "-vframes", "1",
                "-q:v", "2",
                "-loglevel", "error",
                of.name,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            await process.communicate()
            with open(of.name, "rb") as f:
                return f.read()
        finally:
            for tmp in [vf, of]:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    async def extract_preview(
        self,
        video_data: bytes,
        duration_s: float = 3.0,
    ) -> bytes:
        import subprocess
        import tempfile
        import os

        vf = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        of = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        try:
            vf.write(video_data)
            vf.flush()
            of.close()

            cmd = [
                "ffmpeg", "-y",
                "-i", vf.name,
                "-t", f"{duration_s:.3f}",
                "-c", "copy",
                "-loglevel", "error",
                of.name,
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            await process.communicate()
            with open(of.name, "rb") as f:
                return f.read()
        finally:
            for tmp in [vf, of]:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    # ── Persistence ────────────────────────────────────────────────────

    async def save_video(
        self,
        project_id: uuid.UUID,
        scene_id: uuid.UUID,
        video_data: bytes,
        audio_data: bytes | None,
        prompt: str,
        negative_prompt: str,
        seed: int,
        fps: int,
        params_dict: dict,
        provider: str,
        batch_id: uuid.UUID | None = None,
    ) -> Any:
        provider_name = provider or self._provider.__class__.__name__.replace("Adapter", "").lower()

        # Upload video to MinIO
        video_object = f"projects/{project_id}/videos/{scene_id}_{uuid.uuid4().hex[:8]}.mp4"
        video_path = await self._upload_media(video_object, video_data, "video/mp4")

        # Composite audio
        audio_path = None
        audio_duration = None
        if audio_data:
            try:
                composited = await self.composite_audio(video_data, audio_data)
                audio_object = f"projects/{project_id}/videos/{scene_id}_audio_{uuid.uuid4().hex[:8]}.mp4"
                audio_path = await self._upload_media(audio_object, composited, "video/mp4")
                audio_duration = float(len(audio_data)) / 32000.0 * 1000  # 16-bit mono 16kHz
            except Exception as e:
                logger.warning("audio composite failed for %s: %s", scene_id, e)

        # Extract thumbnail
        thumbnail_path = None
        try:
            thumb = await self.extract_thumbnail(video_data)
            thumb_object = f"projects/{project_id}/videos/{scene_id}_thumb.jpg"
            thumbnail_path = await self._upload_media(thumb_object, thumb, "image/jpeg")
        except Exception as e:
            logger.warning("thumbnail extract failed: %s", e)

        # Extract preview
        preview_path = None
        try:
            preview = await self.extract_preview(video_data)
            preview_object = f"projects/{project_id}/videos/{scene_id}_preview.mp4"
            preview_path = await self._upload_media(preview_object, preview, "video/mp4")
        except Exception as e:
            logger.warning("preview extract failed: %s", e)

        # Derive metadata
        duration_s = float(len(video_data)) / 100000.0  # rough estimate
        resolution = f"{params_dict.get('width', 768)}x{params_dict.get('height', 1152)}"

        from domain.models import Video
        video = Video(
            project_id=project_id,
            scene_id=scene_id,
            file_path=video_path,
            duration=duration_s,
            fps=fps,
            resolution=resolution,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            generation_params=params_dict,
            provider=provider_name,
            preview_path=preview_path,
            thumbnail_path=thumbnail_path,
            batch_id=batch_id,
            selected=True,
            version=1,
            audio_path=audio_path,
            audio_duration=audio_duration,
            file_size=len(video_data),
            status="completed",
        )
        saved = await self._videos.create(video)
        logger.info("saved video %s for scene %s", str(saved.id), scene_id)
        return saved

    # ── Cache ─────────────────────────────────────────────────────────

    @staticmethod
    def build_video_cache_key(project_id: str, scene_id: str,
                              character_name: str, seed: int,
                              params_hash: str) -> str:
        content = f"{project_id}|{scene_id}|{character_name}|{seed}|{params_hash}"
        return f"video:result:{CacheService.hash_content(content)}"

    @staticmethod
    def build_prompt_cache_key(project_id: str, scene_id: str,
                               storyboard_hash: str) -> str:
        return f"video:prompt:{project_id}:{scene_id}:{storyboard_hash}"

    # ── Helpers ───────────────────────────────────────────────────────

    async def _upload_media(self, object_name: str, data: bytes, content_type: str) -> str:
        try:
            from infra.minio import upload_file
            await upload_file(object_name, data, content_type)
        except Exception as e:
            logger.warning("MinIO upload failed (%s), storing path only: %s", e, object_name)
        return object_name

    async def _resolve_provider(self) -> str:
        provider_name = self._provider.__class__.__name__.replace("Adapter", "").lower()
        return provider_name
