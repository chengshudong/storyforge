import uuid

from sqlalchemy import select, update
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

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Video]:
        result = await self.session.execute(
            select(Video).where(Video.project_id == project_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def get_selected(self, scene_id: uuid.UUID) -> Video | None:
        result = await self.session.execute(
            select(Video).where(
                Video.scene_id == scene_id,
                Video.selected == True,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_version(self, scene_id: uuid.UUID, version: int) -> Video | None:
        result = await self.session.execute(
            select(Video).where(
                Video.scene_id == scene_id,
                Video.version == version,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def set_selected(self, scene_id: uuid.UUID, video_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Video).where(
                Video.scene_id == scene_id,
                Video.selected == True,
            ).values(selected=False)
        )
        await self.session.execute(
            update(Video).where(Video.id == video_id).values(selected=True)
        )
        await self.session.flush()
