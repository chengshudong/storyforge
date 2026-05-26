from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from api.v1.schemas import AssetGenerationParams
from domain.models import Asset, AssetType, ProjectStatus
from infra.minio import upload_file
from interfaces.image import ImageProvider, ImageResult
from prompts.image import (
    BackgroundPrompt,
    CharacterRefPrompt,
    CharacterScenePrompt,
    CoverPrompt,
    PropPrompt,
)
from providers.image.comfyui_adapter import InstantIDWorkflow
from repository.asset_repository import AssetRepository

logger = logging.getLogger(__name__)


class ImageAgent:
    """Orchestrates deterministic image generation via ComfyUI.

    Does NOT use LLM calls — all prompts are constructed from structured
    character profile and scene storyboard data via deterministic templates.

    Provides atomic per-generation methods. Phase ordering and concurrency
    are handled by the workflow layer.
    """

    def __init__(
        self,
        image_provider: ImageProvider,
        asset_repo: AssetRepository,
    ) -> None:
        self._provider = image_provider
        self._assets = asset_repo

    # ── Generation submission methods ──────────────────────────────────────

    async def generate_char_ref(
        self,
        name: str,
        profile: dict,
        seed: int,
        params: AssetGenerationParams,
    ) -> str:
        """Submit a character reference portrait generation. Returns prompt_id."""
        rendered = CharacterRefPrompt().render(name, profile)
        checkpoint = params.checkpoint or "sd_xl_base_1.0.safetensors"
        workflow = InstantIDWorkflow.build_character_ref_workflow(
            prompt=rendered["positive"],
            negative_prompt=rendered["negative"],
            seed=seed,
            width=params.width,
            height=params.height,
            steps=params.steps,
            cfg=params.cfg,
            sampler=params.sampler,
            checkpoint=checkpoint,
        )
        prompt_id = await self._provider.generate(workflow)
        logger.info("char_ref submitted: %s → prompt_id=%s", name, prompt_id)
        return prompt_id

    async def generate_char_scene(
        self,
        name: str,
        profile: dict,
        storyboard: dict,
        face_image_filename: str,
        seed: int,
        params: AssetGenerationParams,
        action: str = "",
    ) -> str:
        """Submit a character-in-scene generation with InstantID. Returns prompt_id."""
        rendered = CharacterScenePrompt().render(name, profile, storyboard, action)
        checkpoint = params.checkpoint or "sd_xl_base_1.0.safetensors"
        workflow = InstantIDWorkflow.build_instantid_workflow(
            prompt=rendered["positive"],
            negative_prompt=rendered["negative"],
            face_image_filename=face_image_filename,
            seed=seed,
            width=params.width,
            height=params.height,
            steps=params.steps,
            cfg=params.cfg,
            sampler=params.sampler,
            checkpoint=checkpoint,
        )
        prompt_id = await self._provider.generate(workflow)
        logger.info("char_scene submitted: %s → prompt_id=%s", name, prompt_id)
        return prompt_id

    async def generate_background(
        self,
        storyboard: dict,
        seed: int,
        params: AssetGenerationParams,
    ) -> str:
        """Submit a background generation. Returns prompt_id."""
        rendered = BackgroundPrompt().render(storyboard)
        checkpoint = params.checkpoint or "sd_xl_base_1.0.safetensors"
        workflow = InstantIDWorkflow.build_character_ref_workflow(
            prompt=rendered["positive"],
            negative_prompt=rendered["negative"],
            seed=seed,
            width=params.width,
            height=params.height,
            steps=params.steps,
            cfg=params.cfg,
            sampler=params.sampler,
            checkpoint=checkpoint,
        )
        prompt_id = await self._provider.generate(workflow)
        logger.info("bg submitted: %s → prompt_id=%s", storyboard.get("location", "unknown"), prompt_id)
        return prompt_id

    async def generate_prop(
        self,
        name: str,
        description: str,
        prop_type: str,
        seed: int,
        params: AssetGenerationParams,
    ) -> str:
        """Submit a prop image generation. Returns prompt_id."""
        rendered = PropPrompt().render(name, description, prop_type)
        checkpoint = params.checkpoint or "sd_xl_base_1.0.safetensors"
        workflow = InstantIDWorkflow.build_character_ref_workflow(
            prompt=rendered["positive"],
            negative_prompt=rendered["negative"],
            seed=seed,
            width=params.width,
            height=params.height,
            steps=params.steps,
            cfg=params.cfg,
            sampler=params.sampler,
            checkpoint=checkpoint,
        )
        prompt_id = await self._provider.generate(workflow)
        logger.info("prop submitted: %s → prompt_id=%s", name, prompt_id)
        return prompt_id

    async def generate_cover(
        self,
        title: str,
        description: str = "",
        world_setting: str = "",
        key_characters: str = "",
        mood: str = "epic cinematic dramatic",
        seed: int = 0,
        params: AssetGenerationParams = AssetGenerationParams(),
    ) -> str:
        """Submit a cover image generation. Returns prompt_id."""
        rendered = CoverPrompt().render(title, description, world_setting, key_characters, mood)
        checkpoint = params.checkpoint or "sd_xl_base_1.0.safetensors"
        workflow = InstantIDWorkflow.build_character_ref_workflow(
            prompt=rendered["positive"],
            negative_prompt=rendered["negative"],
            seed=seed,
            width=params.width,
            height=params.height,
            steps=params.steps,
            cfg=params.cfg,
            sampler=params.sampler,
            checkpoint=checkpoint,
        )
        prompt_id = await self._provider.generate(workflow)
        logger.info("cover submitted: %s → prompt_id=%s", title, prompt_id)
        return prompt_id

    # ── Polling ────────────────────────────────────────────────────────────

    async def poll(self, prompt_id: str) -> ImageResult:
        """Poll ComfyUI for generation completion."""
        return await self._provider.poll(prompt_id)

    # ── Reference image upload (for InstantID) ─────────────────────────────

    async def upload_face_ref(self, filename: str, data: bytes) -> str:
        """Upload a reference portrait to ComfyUI for InstantID face consistency."""
        return await self._provider.upload_image(filename, data)

    # ── Persistence ────────────────────────────────────────────────────────

    async def save_asset(
        self,
        project_id: uuid.UUID,
        asset_type: AssetType,
        image_data: bytes,
        filename: str,
        prompt: str,
        negative_prompt: str,
        seed: int,
        params_dict: dict,
        character_id: uuid.UUID | None = None,
        scene_id: uuid.UUID | None = None,
        variation_of: uuid.UUID | None = None,
        batch_id: uuid.UUID | None = None,
    ) -> Asset:
        """Persist a generated image to MinIO and create an Asset record."""
        object_name = f"projects/{project_id}/assets/{filename}"
        await upload_file(object_name, image_data, "image/png")

        asset = Asset(
            project_id=project_id,
            character_id=character_id,
            scene_id=scene_id,
            asset_type=asset_type,
            file_path=object_name,
            file_size=len(image_data),
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            generation_params=params_dict,
            variation_of=variation_of,
            batch_id=batch_id,
            status=ProjectStatus.COMPLETED,
            updated_at=datetime.now(timezone.utc),
        )
        saved = await self._assets.create(asset)
        logger.info("asset saved: %s (type=%s, size=%d)", object_name, asset_type.value, len(image_data))
        return saved
