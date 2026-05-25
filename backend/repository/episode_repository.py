import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Episode
from repository.base import BaseRepository


class EpisodeRepository(BaseRepository[Episode]):
    model = Episode

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Episode]:
        result = await self.session.execute(
            select(Episode)
            .where(Episode.project_id == project_id)
            .order_by(Episode.episode_number)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_number(self, project_id: uuid.UUID, episode_number: int) -> Episode | None:
        result = await self.session.execute(
            select(Episode).where(
                Episode.project_id == project_id,
                Episode.episode_number == episode_number,
            )
        )
        return result.scalar_one_or_none()
