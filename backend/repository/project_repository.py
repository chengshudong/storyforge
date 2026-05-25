import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Project, ProjectStatus
from repository.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def list_by_status(self, status: ProjectStatus, offset: int = 0, limit: int = 100) -> list[Project]:
        result = await self.session.execute(
            select(Project).where(Project.status == status).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def update_status(self, project_id: uuid.UUID, status: ProjectStatus) -> Project | None:
        project = await self.get(project_id)
        if project is None:
            return None
        project.status = status
        await self.session.flush()
        return project
