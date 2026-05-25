import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Video
from repository.base import BaseRepository


class VideoRepository(BaseRepository[Video]):
    model = Video

    async def list_by_scene(self, scene_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Video]:
        result = await self.session.execute(
            select(Video).where(Video.scene_id == scene_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
