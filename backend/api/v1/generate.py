from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    EpisodeListResponse,
    EpisodeResponse,
    StoryGenerateRequest,
    StoryGenerateResponse,
)
from domain.models import ProjectStatus
from infra.database import get_db
from infra.queue import create_job
from repository.episode_repository import EpisodeRepository
from repository.project_repository import ProjectRepository
from service.project_service import ProjectService

router = APIRouter(prefix="/generate", tags=["generate"])

EPISODE_PREFIX = "/episodes"
episode_router = APIRouter(prefix=EPISODE_PREFIX, tags=["episodes"])


@router.post("/story", response_model=StoryGenerateResponse, status_code=202)
async def generate_story(
    req: StoryGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> StoryGenerateResponse:
    project = await ProjectService(db).get_project(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.meta or not project.meta.get("collection"):
        raise HTTPException(
            status_code=400,
            detail="Project has no parsed novel data. Run POST /projects/parse first.",
        )

    job = await create_job(db, req.project_id, "story_generation")
    project.status = ProjectStatus.SUMMARIZING
    await db.flush()

    # Trigger Celery task
    from infra.celery_app import app as celery_app

    celery_app.send_task(
        "workflows.story_generation.run",
        args=[str(req.project_id), str(job.id), req.regenerate],
    )

    return StoryGenerateResponse(
        job_id=job.id,
        status="pending",
        message="Story generation started",
    )


@episode_router.get("", response_model=EpisodeListResponse)
async def list_episodes(
    project_id: uuid.UUID = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> EpisodeListResponse:
    repo = EpisodeRepository(db)
    episodes = await repo.list_by_project(project_id, offset=offset, limit=limit)
    total = len(episodes)
    project_repo = ProjectRepository(db)
    project = await project_repo.get(project_id)
    episode_plan = (project.meta or {}).get("episode_plan", []) if project else []

    items = []
    for ep in episodes:
        extra = {}
        for plan_ep in episode_plan:
            if plan_ep.get("episode_number") == ep.episode_number:
                extra = {
                    "chapter_range": plan_ep.get("chapter_range"),
                    "cliffhanger": plan_ep.get("cliffhanger"),
                    "key_scenes": plan_ep.get("key_scenes"),
                }
                break
        items.append(EpisodeResponse(
            id=ep.id,
            episode_number=ep.episode_number,
            title=ep.title,
            summary=ep.summary,
            status=ep.status.value if hasattr(ep.status, "value") else str(ep.status),
            created_at=ep.created_at,
            updated_at=ep.updated_at,
            **extra,
        ))

    return EpisodeListResponse(items=items, total=total, offset=offset, limit=limit)


@episode_router.get("/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
    episode_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EpisodeResponse:
    repo = EpisodeRepository(db)
    episode = await repo.get(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    project_repo = ProjectRepository(db)
    project = await project_repo.get(episode.project_id)
    episode_plan = (project.meta or {}).get("episode_plan", []) if project else []

    extra: dict = {}
    for plan_ep in episode_plan:
        if plan_ep.get("episode_number") == episode.episode_number:
            extra = {
                "chapter_range": plan_ep.get("chapter_range"),
                "cliffhanger": plan_ep.get("cliffhanger"),
                "key_scenes": plan_ep.get("key_scenes"),
            }
            break

    return EpisodeResponse(
        id=episode.id,
        episode_number=episode.episode_number,
        title=episode.title,
        summary=episode.summary,
        status=episode.status.value if hasattr(episode.status, "value") else str(episode.status),
        created_at=episode.created_at,
        updated_at=episode.updated_at,
        **extra,
    )
