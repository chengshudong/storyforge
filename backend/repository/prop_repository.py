from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Prop
from repository.base import BaseRepository


class PropRepository(BaseRepository[Prop]):
    model = Prop

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 200) -> list[Prop]:
        result = await self.session.execute(
            select(Prop).where(Prop.project_id == project_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_scene(self, scene_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Prop]:
        result = await self.session.execute(
            select(Prop).where(Prop.scene_id == scene_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
