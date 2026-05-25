import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Job, JobStatus, Log
from infra.celery_app import app as celery_app
from repository.job_repository import JobRepository


async def create_job(
    session: AsyncSession,
    project_id: uuid.UUID,
    job_type: str,
) -> Job:
    repo = JobRepository(session)
    job = Job(
        project_id=project_id,
        job_type=job_type,
        status=JobStatus.PENDING,
        progress=0,
    )
    await repo.create(job)
    await repo.add_log(job.id, "INFO", f"Job {job_type} created")
    return job


async def update_job_progress(
    session: AsyncSession,
    job_id: uuid.UUID,
    progress: int,
    message: Optional[str] = None,
) -> Job | None:
    repo = JobRepository(session)
    job = await repo.update_progress(job_id, progress)
    if job and message:
        await repo.add_log(job_id, "INFO", message)
    return job


async def complete_job(session: AsyncSession, job_id: uuid.UUID, result: dict | None = None) -> Job | None:
    repo = JobRepository(session)
    job = await repo.update_status(job_id, JobStatus.COMPLETED)
    if job:
        job.progress = 100
        if result:
            job.result = result
        await repo.add_log(job_id, "INFO", "Job completed")
        await session.flush()
    return job


async def fail_job(session: AsyncSession, job_id: uuid.UUID, error: str) -> Job | None:
    repo = JobRepository(session)
    job = await repo.update_status(job_id, JobStatus.FAILED)
    if job:
        job.error = error
        await repo.add_log(job_id, "ERROR", error)
        await session.flush()
    return job


async def cancel_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if job is None:
        return None
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
    job.status = JobStatus.CANCELLED
    await repo.add_log(job_id, "INFO", "Job cancelled")
    await session.flush()
    return job


async def retry_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if job is None:
        return None
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        return None
    job.status = JobStatus.PENDING
    job.progress = 0
    job.error = None
    job.celery_task_id = None
    await repo.add_log(job_id, "INFO", "Job retry requested")
    await session.flush()
    return job


async def get_job_progress(session: AsyncSession, job_id: uuid.UUID) -> dict | None:
    repo = JobRepository(session)
    job = await repo.get(job_id)
    if job is None:
        return None
    return {
        "job_id": str(job.id),
        "job_type": job.job_type,
        "status": job.status.value,
        "progress": job.progress,
        "error": job.error,
    }
