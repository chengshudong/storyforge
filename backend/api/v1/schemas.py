import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from domain.models import JobStatus, ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    source_file: Optional[str] = None
    source_format: Optional[str] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    source_file: Optional[str]
    source_format: Optional[str]
    status: ProjectStatus
    meta: Optional[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    offset: int
    limit: int


class JobResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    status: JobStatus
    progress: int
    result: Optional[dict]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    offset: int
    limit: int
