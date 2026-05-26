from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.schemas import (
    CharacterEditRequest,
    CharacterGenerateRequest,
    CharacterGenerateResponse,
    CharacterListResponse,
    CharacterProfileSchema,
    CharacterResponse,
    CharacterRollbackRequest,
    CharacterSelectRequest,
    CharacterVersionListResponse,
    CharacterVersionSchema,
)
from infra.database import get_db
from infra.queue import create_job
from repository.character_repository import CharacterRepository
from repository.project_repository import ProjectRepository

router = APIRouter(prefix="/characters", tags=["characters"])


def _character_to_response(c: "Character") -> CharacterResponse:
    profile = None
    if c.profile:
        profile = CharacterProfileSchema(**c.profile)
    return CharacterResponse(
        id=c.id,
        project_id=c.project_id,
        name=c.name,
        description=c.description,
        role=c.role,
        traits=c.traits,
        profile=profile,
        version=c.version,
        locked=c.locked,
        locked_at=c.locked_at,
        locked_by=c.locked_by,
        status=c.status.value if hasattr(c.status, "value") else str(c.status),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.post("/generate", response_model=CharacterGenerateResponse, status_code=202)
async def generate_characters(
    req: CharacterGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> CharacterGenerateResponse:
    project_repo = ProjectRepository(db)
    project = await project_repo.get(req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.meta:
        raise HTTPException(status_code=400, detail="Project has no parsed data")

    job = await create_job(db, req.project_id, "character_generation")

    from infra.celery_app import app as celery_app
    celery_app.send_task(
        "workflows.character_generation.run",
        args=[str(req.project_id), str(job.id), req.regenerate],
    )

    return CharacterGenerateResponse(
        job_id=job.id,
        status="pending",
        message="Character generation started",
    )


@router.post("/select", response_model=CharacterListResponse)
async def select_characters(
    req: CharacterSelectRequest,
    db: AsyncSession = Depends(get_db),
) -> CharacterListResponse:
    repo = CharacterRepository(db)
    updated = []
    for cid in req.character_ids:
        character = await repo.get(cid)
        if character is None:
            raise HTTPException(status_code=404, detail=f"Character {cid} not found")
        if character.locked and not req.approved:
            raise HTTPException(status_code=409, detail=f"Character {character.name} is already locked")

        character.locked = req.approved
        if req.approved:
            character.locked_at = datetime.now(timezone.utc)
            character.locked_by = "user"
        updated.append(character)

    await db.flush()
    items = [_character_to_response(c) for c in updated]
    return CharacterListResponse(items=items, total=len(items), offset=0, limit=len(items))


@router.get("", response_model=CharacterListResponse)
async def list_characters(
    project_id: uuid.UUID = Query(...),
    role: str | None = Query(None),
    locked: bool | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> CharacterListResponse:
    repo = CharacterRepository(db)
    characters = await repo.list_by_project(project_id, offset=offset, limit=limit,
                                            role=role, locked=locked)
    total = await repo.count_by_project(project_id, role=role, locked=locked)
    items = [_character_to_response(c) for c in characters]
    return CharacterListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    repo = CharacterRepository(db)
    character = await repo.get(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    return _character_to_response(character)


@router.get("/{character_id}/versions", response_model=CharacterVersionListResponse)
async def list_character_versions(
    character_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CharacterVersionListResponse:
    repo = CharacterRepository(db)
    character = await repo.get(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")

    versions = await repo.list_versions(character_id)
    items = [
        CharacterVersionSchema(
            id=v.id,
            version_number=v.version_number,
            profile_snapshot=v.profile_snapshot,
            diff=v.diff,
            created_at=v.created_at,
            created_by=v.created_by,
        )
        for v in versions
    ]
    return CharacterVersionListResponse(items=items, total=len(items))


@router.patch("/{character_id}", response_model=CharacterResponse)
async def edit_character(
    character_id: uuid.UUID,
    req: CharacterEditRequest,
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    repo = CharacterRepository(db)
    character = await repo.get(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")

    # Handle unlock request
    if req.unlock:
        if not character.locked:
            raise HTTPException(status_code=409, detail="Character is not locked")
        character.locked = False
        character.locked_at = None
        character.locked_by = None
        await db.flush()
        return _character_to_response(character)

    # Lock check
    if character.locked:
        raise HTTPException(status_code=409, detail="Character is locked — unlock first")

    # If feedback provided, regenerate via LLM
    if req.feedback and character.profile:
        try:
            from agents.character_agent import CharacterAgent
            from services.cache_service import CacheService
            from services.model_router.router import ModelRouter
            from services.model_router.secret_loader import SecretLoader
            from providers.llm.deepseek import DeepSeekAdapter
            from providers.llm.openai import OpenAIAdapter
            from providers.llm.anthropic import AnthropicAdapter
            from providers.llm.gemini import GeminiAdapter
            from providers.llm.openrouter import OpenRouterAdapter
            from providers.llm.local import LocalAdapter
            from providers.vector.qdrant_adapter import QdrantAdapter
            import yaml
            from pathlib import Path

            config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
            with open(config_path, encoding="utf-8") as f:
                registry = yaml.safe_load(f)

            provider_map = {
                "deepseek": DeepSeekAdapter(), "openai": OpenAIAdapter(),
                "anthropic": AnthropicAdapter(), "gemini": GeminiAdapter(),
                "openrouter": OpenRouterAdapter(), "local": LocalAdapter(),
            }
            agent = CharacterAgent(
                ModelRouter(provider_map, registry),
                CacheService(),
                QdrantAdapter(),
            )

            # Build profile prompt from current character + feedback
            from prompts.character import CharacterProfilePrompt
            prompt = CharacterProfilePrompt().render(
                name=character.name,
                role=character.role or "",
                importance="",
                narrative_function=character.description or "",
                chapter_context=json.dumps({"feedback": req.feedback}),
                relationships="[]",
                scene_context="[]",
                world_setting="{}",
            )

            text, _ = await agent._call_llm(
                task="character",
                system_prompt=prompt["system"],
                user_prompt=prompt["user"],
                project_id=str(character.project_id),
            )
            regenerated = CharacterAgent._parse_json(text, character.profile or {})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Character regeneration failed: {e}")

        # Build diff between old and new profile
        old_profile = character.profile or {}
        diff = {}
        for key in set(list(old_profile.keys()) + list(regenerated.keys())):
            if key.startswith("_"):
                continue
            old_val = old_profile.get(key)
            new_val = regenerated.get(key)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}

        # Create new version
        new_version = character.version + 1
        await repo.create_version(
            character_id=character.id,
            version_number=new_version,
            profile_snapshot=regenerated,
            diff=diff,
            created_by="user",
        )

        character.profile = regenerated
        character.version = new_version
        character.locked = False  # unlock after edit for re-approval

    # Apply direct edits
    old_profile = dict(character.profile or {}) if character.profile else {}
    profile_changed = False

    if req.name is not None:
        character.name = req.name
    if req.description is not None:
        character.description = req.description
    if req.role is not None:
        character.role = req.role
    if req.traits is not None:
        character.traits = req.traits
    if req.profile is not None:
        profile_data = req.profile.model_dump(exclude_none=True)
        if character.profile:
            character.profile = {**character.profile, **profile_data}
        else:
            character.profile = profile_data
        profile_changed = True

    # If profile was directly edited (not via feedback), create version
    if profile_changed and not req.feedback:
        new_version = character.version + 1
        diff = {}
        for key in set(list(old_profile.keys()) + list((character.profile or {}).keys())):
            if key.startswith("_"):
                continue
            old_val = old_profile.get(key)
            new_val = (character.profile or {}).get(key)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}

        await repo.create_version(
            character_id=character.id,
            version_number=new_version,
            profile_snapshot=character.profile,
            diff=diff,
            created_by="user",
        )
        character.version = new_version

    await db.flush()
    return _character_to_response(character)


@router.post("/{character_id}/rollback", response_model=CharacterResponse)
async def rollback_character(
    character_id: uuid.UUID,
    req: CharacterRollbackRequest,
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    repo = CharacterRepository(db)
    character = await repo.get(character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="Character not found")
    if character.locked:
        raise HTTPException(status_code=409, detail="Character is locked — unlock first")

    target = await repo.get_version(character_id, req.version)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Version {req.version} not found")

    old_profile = character.profile or {}
    new_version = character.version + 1

    await repo.create_version(
        character_id=character.id,
        version_number=new_version,
        profile_snapshot=target.profile_snapshot,
        diff={"rollback": {"from_version": character.version, "to_version": req.version}},
        created_by="user",
    )

    character.profile = target.profile_snapshot
    character.version = new_version
    character.locked = False

    await db.flush()
    return _character_to_response(character)
