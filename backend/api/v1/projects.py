from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database import get_db
from service.project_service import ProjectService
from api.v1.schemas import ProjectCreate, ProjectResponse, ProjectListResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    service = ProjectService(db)
    project = await service.create_project(data)
    return project


@router.get("", response_model=ProjectListResponse)
async def list_projects(offset: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    service = ProjectService(db)
    projects, total = await service.list_projects(offset=offset, limit=limit)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    from uuid import UUID
    service = ProjectService(db)
    project = await service.get_project(UUID(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
