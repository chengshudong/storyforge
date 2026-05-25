import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Asset, AssetType
from repository.base import BaseRepository


class AssetRepository(BaseRepository[Asset]):
    model = Asset

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Asset]:
        result = await self.session.execute(
            select(Asset).where(Asset.project_id == project_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_type(self, project_id: uuid.UUID, asset_type: AssetType, offset: int = 0, limit: int = 100) -> list[Asset]:
        result = await self.session.execute(
            select(Asset)
            .where(Asset.project_id == project_id, Asset.asset_type == asset_type)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_character(self, character_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Asset]:
        result = await self.session.execute(
            select(Asset).where(Asset.character_id == character_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_scene(self, scene_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Asset]:
        result = await self.session.execute(
            select(Asset).where(Asset.scene_id == scene_id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
