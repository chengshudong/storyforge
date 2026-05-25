import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Project, ProjectStatus
from repository.project_repository import ProjectRepository
from api.v1.schemas import ProjectCreate


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.repo = ProjectRepository(session)
        self.session = session

    async def create_project(self, data: ProjectCreate) -> Project:
        project = Project(
            name=data.name,
            description=data.description,
            source_file=data.source_file,
            source_format=data.source_format,
            status=ProjectStatus.PENDING,
        )
        return await self.repo.create(project)

    async def get_project(self, project_id: uuid.UUID) -> Project | None:
        return await self.repo.get(project_id)

    async def list_projects(self, offset: int = 0, limit: int = 100) -> tuple[list[Project], int]:
        projects = await self.repo.list(offset=offset, limit=limit)
        total = await self.repo.count()
        return projects, total
