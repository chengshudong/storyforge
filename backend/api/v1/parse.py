from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import ParseUploadResponse, ProjectCreate
from domain.models import ProjectStatus
from infra.database import get_db
from infra.minio import upload_file
from service.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["parse"])


@router.post("/parse", response_model=ParseUploadResponse, status_code=201)
async def parse_novel(
    file: UploadFile = File(...),
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> ParseUploadResponse:
    allowed_formats = {"txt", "docx", "epub"}
    suffix = Path(file.filename or "unknown").suffix.lstrip(".").lower()
    file_format = suffix if suffix in allowed_formats else None
    if file_format is None:
        allowed = ", ".join(f".{f}" for f in sorted(allowed_formats))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")

    contents = await file.read()
    object_name = f"uploads/{uuid.uuid4()}.{file_format}"
    await upload_file(object_name, contents, file.content_type or "application/octet-stream")

    service = ProjectService(db)
    project = await service.create_project(
        ProjectCreate(name=name, source_file=object_name, source_format=file_format)
    )
    project.status = ProjectStatus.PARSING
    await db.flush()

    import tempfile
    import os

    tmp_path = ""
    try:
        suffix = f".{file_format}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        from providers.novel.unstructured_adapter import UnstructuredAdapter
        from providers.context.llamaindex_adapter import LlamaIndexAdapter
        from providers.vector.qdrant_adapter import QdrantAdapter
        from agents.novel_agent import NovelAgent

        parser = UnstructuredAdapter()
        vector_store = QdrantAdapter()
        context_store = LlamaIndexAdapter(vector_store)
        agent = NovelAgent(parser, context_store, vector_store)

        result = await agent.process(tmp_path, file_format, str(project.id))

        project.status = ProjectStatus.PARSING
        project.meta = {
            "chunk_count": result["chunk_count"],
            "char_count": result["char_count"],
            "entities": result["entities"],
            "collection": result["collection"],
        }
        await db.flush()

        return ParseUploadResponse(
            project_id=project.id,
            title=result["title"],
            char_count=result["char_count"],
            chunk_count=result["chunk_count"],
            entities=result["entities"],
            collection=result["collection"],
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
