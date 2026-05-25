import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Character
from repository.base import BaseRepository


class CharacterRepository(BaseRepository[Character]):
    model = Character

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Character]:
        result = await self.session.execute(
            select(Character)
            .where(Character.project_id == project_id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_name(self, project_id: uuid.UUID, name: str) -> Character | None:
        result = await self.session.execute(
            select(Character).where(
                Character.project_id == project_id,
                Character.name == name,
            )
        )
        return result.scalar_one_or_none()
