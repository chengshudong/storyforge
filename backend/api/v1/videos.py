from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoListResponse,
    VideoResponse,
    VideoSelectRequest,
)
from infra.database import get_db
from infra.queue import create_job
from repository.project_repository import ProjectRepository
from repository.video_repository import VideoRepository

router = APIRouter(prefix="/videos", tags=["videos"])


def _video_to_response(v: "Video") -> VideoResponse:
    from domain.models import Video
    return VideoResponse(
        id=v.id,
        project_id=v.project_id,
        scene_id=v.scene_id,
        file_path=v.file_path,
        duration=v.duration,
        resolution=v.resolution,
        prompt=v.prompt,
        negative_prompt=v.negative_prompt,
        seed=v.seed,
        fps=v.fps or 24,
        generation_params=v.generation_params,
        provider=v.provider,
        preview_path=v.preview_path,
        thumbnail_path=v.thumbnail_path,
        batch_id=v.batch_id,
        selected=v.selected if v.selected is not None else False,
        version=v.version or 1,
        audio_path=v.audio_path,
        audio_duration=v.audio_duration,
        file_size=v.file_size,
        status=v.status.value if hasattr(v.status, "value") else str(v.status),
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.post("/generate", response_model=VideoGenerateResponse, status_code=202)
async def generate_videos(
    req: VideoGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> VideoGenerateResponse:
    project_repo = ProjectRepository(db)
    project = await project_repo.get(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    job = await create_job(db, req.project_id, "video_generation")

    from infra.celery_app import app as celery_app
    celery_app.send_task(
        "workflows.video_generation.run",
        args=[str(req.project_id), str(job.id), req.phases, req.variant_count, req.regenerate],
    )

    batch_id = uuid.uuid4()
    return VideoGenerateResponse(
        job_id=job.id,
        batch_id=batch_id,
        status="pending",
        message=f"Video generation started for phases: {req.phases}",
    )


@router.get("", response_model=VideoListResponse)
async def list_videos(
    project_id: uuid.UUID = Query(...),
    scene_id: uuid.UUID | None = Query(None),
    selected: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    repo = VideoRepository(db)
    if scene_id:
        videos = await repo.list_by_scene(scene_id, offset=offset, limit=limit)
    else:
        videos = await repo.list_by_project(project_id, offset=offset, limit=limit)

    if selected is not None:
        videos = [v for v in videos if v.selected == selected]

    items = [_video_to_response(v) for v in videos]
    return VideoListResponse(items=items, total=len(items), offset=offset, limit=limit)


@router.post("/select", response_model=VideoListResponse)
async def select_videos(
    req: VideoSelectRequest,
    db: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    repo = VideoRepository(db)
    updated = []
    for vid in req.video_ids:
        video = await repo.get(vid)
        if video is None:
            raise HTTPException(status_code=404, detail=f"Video {vid} not found")
        video.selected = req.selected
        updated.append(video)

    await db.flush()
    items = [_video_to_response(v) for v in updated]
    return VideoListResponse(items=items, total=len(items), offset=0, limit=len(items))


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> VideoResponse:
    repo = VideoRepository(db)
    video = await repo.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return _video_to_response(video)


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    repo = VideoRepository(db)
    video = await repo.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    try:
        from infra.minio import download_file
        data = await download_file(video.file_path)
        return Response(content=data, media_type="video/mp4")
    except Exception:
        raise HTTPException(status_code=404, detail="Video file not found")


@router.get("/{video_id}/thumbnail")
async def get_video_thumbnail(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    repo = VideoRepository(db)
    video = await repo.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.thumbnail_path:
        try:
            from infra.minio import download_file
            data = await download_file(video.thumbnail_path)
            return Response(content=data, media_type="image/jpeg")
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Thumbnail not found")


@router.get("/{video_id}/preview")
async def get_video_preview(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    repo = VideoRepository(db)
    video = await repo.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.preview_path:
        try:
            from infra.minio import download_file
            data = await download_file(video.preview_path)
            return Response(content=data, media_type="video/mp4")
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Preview not found")


@router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = VideoRepository(db)
    video = await repo.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if hasattr(video, "locked") and video.locked:
        raise HTTPException(status_code=409, detail="Video is locked")
    await repo.delete(video_id)
    await db.flush()
