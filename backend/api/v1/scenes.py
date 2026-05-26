from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    SceneEditRequest,
    SceneGenerateRequest,
    SceneGenerateResponse,
    SceneListResponse,
    SceneResponse,
    SceneStoryboardSchema,
)
from domain.models import ProjectStatus
from infra.database import get_db
from infra.queue import create_job
from repository.episode_repository import EpisodeRepository
from repository.project_repository import ProjectRepository
from repository.scene_repository import SceneRepository

router = APIRouter(prefix="/episodes", tags=["scenes"])

SCENES_PREFIX = "/scenes"
scenes_router = APIRouter(prefix=SCENES_PREFIX, tags=["scenes"])


@router.post("/{episode_id}/scenes", response_model=SceneGenerateResponse, status_code=202)
async def generate_scenes(
    episode_id: uuid.UUID,
    req: SceneGenerateRequest = SceneGenerateRequest(),
    db: AsyncSession = Depends(get_db),
) -> SceneGenerateResponse:
    episode_repo = EpisodeRepository(db)
    episode = await episode_repo.get(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    project = await ProjectRepository(db).get(episode.project_id)
    if project is None or not project.meta:
        raise HTTPException(status_code=400, detail="Project has no parsed data")

    job = await create_job(db, episode.project_id, "scene_generation")
    episode.status = ProjectStatus.SCENES
    await db.flush()

    from infra.celery_app import app as celery_app

    celery_app.send_task(
        "workflows.scene_generation.run",
        args=[str(episode.project_id), str(episode_id), str(job.id), req.regenerate],
    )

    return SceneGenerateResponse(
        job_id=job.id,
        status="pending",
        message=f"Scene generation started for episode {episode.episode_number}",
    )


@scenes_router.get("", response_model=SceneListResponse)
async def list_scenes(
    episode_id: uuid.UUID = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> SceneListResponse:
    repo = SceneRepository(db)
    scenes = await repo.list_by_episode(episode_id, offset=offset, limit=limit)
    total = len(scenes)

    items = []
    for sc in scenes:
        sb = None
        if sc.storyboard:
            sb = SceneStoryboardSchema(**sc.storyboard)
        items.append(SceneResponse(
            id=sc.id,
            episode_id=sc.episode_id,
            scene_number=sc.scene_number,
            title=sc.title,
            description=sc.description,
            dialogue=sc.dialogue,
            storyboard=sb,
            status=sc.status.value if hasattr(sc.status, "value") else str(sc.status),
            created_at=sc.created_at,
            updated_at=sc.updated_at,
        ))

    return SceneListResponse(items=items, total=total, offset=offset, limit=limit)


@scenes_router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(
    scene_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SceneResponse:
    repo = SceneRepository(db)
    scene = await repo.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    sb = None
    if scene.storyboard:
        sb = SceneStoryboardSchema(**scene.storyboard)

    return SceneResponse(
        id=scene.id,
        episode_id=scene.episode_id,
        scene_number=scene.scene_number,
        title=scene.title,
        description=scene.description,
        dialogue=scene.dialogue,
        storyboard=sb,
        status=scene.status.value if hasattr(scene.status, "value") else str(scene.status),
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


@scenes_router.patch("/{scene_id}", response_model=SceneResponse)
async def edit_scene(
    scene_id: uuid.UUID,
    req: SceneEditRequest,
    db: AsyncSession = Depends(get_db),
) -> SceneResponse:
    repo = SceneRepository(db)
    scene = await repo.get(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Check if scene is locked
    if scene.storyboard and scene.storyboard.get("locked"):
        raise HTTPException(status_code=403, detail="Scene is locked and cannot be edited")

    # If feedback provided, regenerate via LLM
    if req.feedback:
        try:
            from agents.scene_agent import SceneAgent
            from services.cache_service import CacheService
            from services.model_router.router import ModelRouter
            from services.model_router.secret_loader import SecretLoader
            from providers.llm.deepseek import DeepSeekAdapter
            from providers.llm.openai import OpenAIAdapter
            from providers.llm.anthropic import AnthropicAdapter
            from providers.llm.gemini import GeminiAdapter
            from providers.llm.openrouter import OpenRouterAdapter
            from providers.llm.local import LocalAdapter
            import yaml
            from pathlib import Path

            config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
            with open(config_path, encoding="utf-8") as f:
                registry = yaml.safe_load(f)

            provider_map = {
                "deepseek": DeepSeekAdapter(), "openai": OpenAIAdapter(),
                "anthropic": AnthropicAdapter(), "gemini": GeminiAdapter(),
                "openrouter": OpenRouterAdapter(), "local": LocalAdapter(),
            }
            agent = SceneAgent(ModelRouter(provider_map, registry), CacheService())

            current = {
                "scene_number": scene.scene_number,
                "scene_title": scene.title,
                "description": scene.description,
                "camera": scene.storyboard.get("camera") if scene.storyboard else "",
                "emotion": scene.storyboard.get("emotion") if scene.storyboard else "",
                "location": scene.storyboard.get("location") if scene.storyboard else "",
                "dialogue": scene.dialogue or [],
                "props": scene.storyboard.get("props", []) if scene.storyboard else [],
                "transition": scene.storyboard.get("transition", "cut") if scene.storyboard else "cut",
                "character_actions": scene.storyboard.get("character_actions", {}) if scene.storyboard else {},
                "asset_refs": scene.storyboard.get("asset_refs", []) if scene.storyboard else [],
                "characters_present": scene.storyboard.get("characters_present", []) if scene.storyboard else [],
                "estimated_duration": scene.storyboard.get("duration", 30) if scene.storyboard else 30,
            }

            # Get adjacent scenes for context
            all_scenes = await repo.list_by_episode(scene.episode_id)
            adjacent = []
            for s in all_scenes:
                if s.scene_number == scene.scene_number - 1 or s.scene_number == scene.scene_number + 1:
                    adjacent.append({
                        "scene_number": s.scene_number,
                        "scene_title": s.title,
                        "description": s.description,
                        "dialogue": s.dialogue,
                        "location": s.storyboard.get("location") if s.storyboard else "",
                    })

            regenerated = await agent.regenerate_scene(
                project_id=str(scene.episode_id),
                scene=current,
                adjacent=adjacent,
                feedback=req.feedback,
            )

            scene.title = regenerated.get("scene_title", scene.title)
            scene.description = regenerated.get("description", scene.description)
            scene.dialogue = regenerated.get("dialogue", scene.dialogue)
            scene.storyboard = {
                "camera": regenerated.get("camera"),
                "duration": regenerated.get("estimated_duration", 30),
                "emotion": regenerated.get("emotion"),
                "location": regenerated.get("location"),
                "props": regenerated.get("props", []),
                "transition": regenerated.get("transition", "cut"),
                "asset_refs": regenerated.get("asset_refs", []),
                "character_actions": regenerated.get("character_actions", {}),
                "characters_present": regenerated.get("characters_present", []),
                "locked": scene.storyboard.get("locked", False) if scene.storyboard else False,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Scene regeneration failed: {e}")

    # Apply direct edits
    if req.title is not None:
        scene.title = req.title
    if req.description is not None:
        scene.description = req.description
    if req.dialogue is not None:
        scene.dialogue = req.dialogue
    if req.storyboard is not None and scene.storyboard:
        sb_data = req.storyboard.model_dump(exclude_none=True)
        scene.storyboard = {**scene.storyboard, **sb_data}

    await db.flush()

    sb = None
    if scene.storyboard:
        sb = SceneStoryboardSchema(**scene.storyboard)

    return SceneResponse(
        id=scene.id,
        episode_id=scene.episode_id,
        scene_number=scene.scene_number,
        title=scene.title,
        description=scene.description,
        dialogue=scene.dialogue,
        storyboard=sb,
        status=scene.status.value if hasattr(scene.status, "value") else str(scene.status),
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )
