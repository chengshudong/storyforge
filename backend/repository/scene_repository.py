import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Scene
from repository.base import BaseRepository


class SceneRepository(BaseRepository[Scene]):
    model = Scene

    async def list_by_episode(self, episode_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Scene]:
        result = await self.session.execute(
            select(Scene)
            .where(Scene.episode_id == episode_id)
            .order_by(Scene.scene_number)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_number(self, episode_id: uuid.UUID, scene_number: int) -> Scene | None:
        result = await self.session.execute(
            select(Scene).where(
                Scene.episode_id == episode_id,
                Scene.scene_number == scene_number,
            )
        )
        return result.scalar_one_or_none()
