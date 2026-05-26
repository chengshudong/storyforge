from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    VoiceGenerateRequest,
    VoiceGenerateResponse,
    VoiceListResponse,
    VoiceResponse,
)
from infra.database import get_db
from infra.queue import create_job
from repository.project_repository import ProjectRepository
from repository.voice_repository import VoiceRepository

router = APIRouter(prefix="/voices", tags=["voices"])


def _voice_to_response(v: "Voice") -> VoiceResponse:
    from domain.models import Voice
    return VoiceResponse(
        voice_id=v.id,
        character_id=v.character_id,
        provider=v.provider or "",
        speaker=v.speaker or "",
        speed=v.speed or 1.0,
        pitch=v.pitch or 0,
        emotion=v.emotion or "neutral",
        version=v.version or 1,
        selected=v.selected if v.selected is not None else False,
        file_path=v.file_path,
        file_size=v.file_size,
        duration_ms=v.duration_ms,
        preview_path=v.preview_path,
        reference_audio_path=v.reference_audio_path,
        scene_id=v.scene_id,
        dialogue_index=v.dialogue_index,
        voice_params=v.voice_params,
        status=v.status.value if hasattr(v.status, "value") else str(v.status),
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


@router.post("/generate", response_model=VoiceGenerateResponse, status_code=202)
async def generate_voices(
    req: VoiceGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> VoiceGenerateResponse:
    project_repo = ProjectRepository(db)
    project = await project_repo.get(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    job = await create_job(db, req.project_id, "voice_generation")

    from infra.celery_app import app as celery_app
    celery_app.send_task(
        "workflows.voice_generation.run",
        args=[str(req.project_id), str(job.id), req.phases, req.regenerate],
    )

    batch_id = uuid.uuid4()
    return VoiceGenerateResponse(
        job_id=job.id,
        batch_id=batch_id,
        status="pending",
        message=f"Voice generation started for phases: {req.phases}",
    )


@router.get("", response_model=VoiceListResponse)
async def list_voices(
    project_id: uuid.UUID = Query(...),
    character_id: uuid.UUID | None = Query(None),
    selected: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> VoiceListResponse:
    repo = VoiceRepository(db)
    if character_id:
        voices = await repo.list_by_character(character_id, offset=offset, limit=limit)
    else:
        voices = await repo.list_by_project(project_id, offset=offset, limit=limit)

    if selected is not None:
        voices = [v for v in voices if v.selected == selected]

    items = [_voice_to_response(v) for v in voices]
    return VoiceListResponse(items=items, total=len(items), offset=offset, limit=limit)


@router.get("/{voice_id}", response_model=VoiceResponse)
async def get_voice(
    voice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> VoiceResponse:
    repo = VoiceRepository(db)
    voice = await repo.get(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="Voice not found")
    return _voice_to_response(voice)


@router.get("/{voice_id}/preview")
async def preview_voice(
    voice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    repo = VoiceRepository(db)
    voice = await repo.get(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="Voice not found")

    if voice.preview_path:
        try:
            from infra.minio import get_file
            data = await get_file(voice.preview_path)
            return Response(content=data, media_type="audio/wav")
        except Exception:
            pass

    # Fallback: serve the main file
    try:
        from infra.minio import get_file
        data = await get_file(voice.file_path)
        return Response(content=data, media_type="audio/wav")
    except Exception:
        raise HTTPException(status_code=404, detail="Audio file not found")


@router.delete("/{voice_id}", status_code=204)
async def delete_voice(
    voice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = VoiceRepository(db)
    voice = await repo.get(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail="Voice not found")
    if voice.locked if hasattr(voice, 'locked') else False:
        raise HTTPException(status_code=409, detail="Voice is locked")
    await repo.delete(voice_id)
    await db.flush()
