import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Voice
from repository.base import BaseRepository


class VoiceRepository(BaseRepository[Voice]):
    model = Voice

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Voice]:
        result = await self.session.execute(
            select(Voice).where(Voice.project_id == project_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_character(self, character_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Voice]:
        result = await self.session.execute(
            select(Voice).where(Voice.character_id == character_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
