from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database import get_db
from service.job_service import JobService
from api.v1.schemas import JobResponse, JobListResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    project_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID
    service = JobService(db)
    if project_id:
        jobs, total = await service.list_jobs_by_project(UUID(project_id), offset=offset, limit=limit)
    else:
        jobs, total = await service.list_jobs(offset=offset, limit=limit)
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    from uuid import UUID
    service = JobService(db)
    job = await service.get_job(UUID(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
