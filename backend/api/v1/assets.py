from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    AssetEditRequest,
    AssetFavoriteRequest,
    AssetGenerateRequest,
    AssetGenerateResponse,
    AssetListResponse,
    AssetResponse,
    AssetSelectRequest,
)
from domain.models import AssetType
from infra.database import get_db
from infra.queue import create_job
from repository.asset_repository import AssetRepository
from repository.project_repository import ProjectRepository

router = APIRouter(prefix="/assets", tags=["assets"])


def _asset_to_response(a: "Asset") -> AssetResponse:
    return AssetResponse(
        id=a.id,
        project_id=a.project_id,
        character_id=a.character_id,
        scene_id=a.scene_id,
        asset_type=a.asset_type.value if hasattr(a.asset_type, "value") else str(a.asset_type),
        file_path=a.file_path,
        file_size=a.file_size,
        prompt=a.prompt,
        negative_prompt=a.negative_prompt,
        seed=a.seed,
        generation_params=a.generation_params,
        variation_of=a.variation_of,
        batch_id=a.batch_id,
        selected=a.selected,
        favorite=a.favorite,
        locked=a.locked,
        locked_at=a.locked_at,
        asset_ref=a.asset_ref,
        status=a.status.value if hasattr(a.status, "value") else str(a.status),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


@router.post("/generate", response_model=AssetGenerateResponse, status_code=202)
async def generate_assets(
    req: AssetGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> AssetGenerateResponse:
    project_repo = ProjectRepository(db)
    project = await project_repo.get(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    job = await create_job(db, req.project_id, "image_generation")

    from infra.celery_app import app as celery_app
    celery_app.send_task(
        "workflows.image_generation.run",
        args=[str(req.project_id), str(job.id), req.phases, req.variant_count, req.regenerate],
    )

    batch_id = uuid.uuid4()
    return AssetGenerateResponse(
        job_id=job.id,
        batch_id=batch_id,
        status="pending",
        message=f"Image generation started for phases: {req.phases}",
    )


@router.post("/select", response_model=AssetListResponse)
async def select_assets(
    req: AssetSelectRequest,
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    repo = AssetRepository(db)
    updated = []
    for aid in req.asset_ids:
        asset = await repo.get(aid)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset {aid} not found")
        asset.selected = req.selected
        updated.append(asset)

    await db.flush()
    items = [_asset_to_response(a) for a in updated]
    return AssetListResponse(items=items, total=len(items), offset=0, limit=len(items))


@router.post("/favorite", response_model=AssetListResponse)
async def favorite_assets(
    req: AssetFavoriteRequest,
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    repo = AssetRepository(db)
    updated = []
    for aid in req.asset_ids:
        asset = await repo.get(aid)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset {aid} not found")
        asset.favorite = req.favorite
        updated.append(asset)

    await db.flush()
    items = [_asset_to_response(a) for a in updated]
    return AssetListResponse(items=items, total=len(items), offset=0, limit=len(items))


@router.get("", response_model=AssetListResponse)
async def list_assets(
    project_id: uuid.UUID = Query(...),
    character_id: uuid.UUID | None = Query(None),
    scene_id: uuid.UUID | None = Query(None),
    asset_type: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    repo = AssetRepository(db)
    if character_id:
        assets = await repo.list_by_character(character_id, offset=offset, limit=limit)
        total = len(assets)
    elif scene_id:
        assets = await repo.list_by_scene(scene_id, offset=offset, limit=limit)
        total = len(assets)
    elif asset_type:
        try:
            at = AssetType(asset_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid asset_type: {asset_type}")
        assets = await repo.list_by_type(project_id, at, offset=offset, limit=limit)
        total = len(assets)
    else:
        assets = await repo.list_by_project(project_id, offset=offset, limit=limit)
        total = len(assets)

    items = [_asset_to_response(a) for a in assets]
    return AssetListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    repo = AssetRepository(db)
    asset = await repo.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _asset_to_response(asset)


@router.patch("/{asset_id}", response_model=AssetResponse)
async def edit_asset(
    asset_id: uuid.UUID,
    req: AssetEditRequest,
    db: AsyncSession = Depends(get_db),
) -> AssetResponse:
    repo = AssetRepository(db)
    asset = await repo.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    if req.locked is not None:
        asset.locked = req.locked
        if req.locked:
            asset.locked_at = datetime.now(timezone.utc)
        else:
            asset.locked_at = None

    # Note: feedback and regenerate require async LLM calls which are handled
    # by triggering a new generate job. The PATCH endpoint just stores feedback.
    if req.feedback is not None:
        gen_params = asset.generation_params or {}
        gen_params["feedback"] = req.feedback
        asset.generation_params = gen_params

    if req.regenerate:
        from infra.queue import create_job as create_job_fn
        from infra.celery_app import app as celery_app
        job = await create_job_fn(db, asset.project_id, "image_generation")
        celery_app.send_task(
            "workflows.image_generation.run",
            args=[str(asset.project_id), str(job.id)],
        )

    await db.flush()
    return _asset_to_response(asset)


@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = AssetRepository(db)
    asset = await repo.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.locked:
        raise HTTPException(status_code=409, detail="Asset is locked")
    await repo.delete(asset_id)
    await db.flush()
