import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Job
from repository.job_repository import JobRepository


class JobService:
    def __init__(self, session: AsyncSession):
        self.repo = JobRepository(session)
        self.session = session

    async def get_job(self, job_id: uuid.UUID) -> Job | None:
        return await self.repo.get(job_id)

    async def list_jobs(self, offset: int = 0, limit: int = 100) -> tuple[list[Job], int]:
        jobs = await self.repo.list(offset=offset, limit=limit)
        total = await self.repo.count()
        return jobs, total

    async def list_jobs_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> tuple[list[Job], int]:
        jobs = await self.repo.list_by_project(project_id, offset=offset, limit=limit)
        return jobs, len(jobs)
