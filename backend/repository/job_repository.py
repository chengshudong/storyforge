import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Job, JobStatus, Log
from repository.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    model = Job

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Job]:
        result = await self.session.execute(
            select(Job).where(Job.project_id == project_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_status(self, status: JobStatus, offset: int = 0, limit: int = 100) -> list[Job]:
        result = await self.session.execute(
            select(Job).where(Job.status == status).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(self, job_id: uuid.UUID, status: JobStatus) -> Job | None:
        job = await self.get(job_id)
        if job is None:
            return None
        job.status = status
        await self.session.flush()
        return job

    async def update_progress(self, job_id: uuid.UUID, progress: int) -> Job | None:
        job = await self.get(job_id)
        if job is None:
            return None
        job.progress = progress
        await self.session.flush()
        return job

    async def add_log(self, job_id: uuid.UUID, level: str, message: str) -> Log:
        log = Log(job_id=job_id, level=level, message=message)
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_logs(self, job_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Log]:
        result = await self.session.execute(
            select(Log).where(Log.job_id == job_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
