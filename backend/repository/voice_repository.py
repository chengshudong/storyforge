import uuid

from sqlalchemy import select, update
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

    async def list_by_scene(self, scene_id: uuid.UUID, offset: int = 0, limit: int = 100) -> list[Voice]:
        result = await self.session.execute(
            select(Voice).where(Voice.scene_id == scene_id)
            .order_by(Voice.dialogue_index).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def get_selected(self, character_id: uuid.UUID) -> Voice | None:
        result = await self.session.execute(
            select(Voice).where(
                Voice.character_id == character_id,
                Voice.selected == True,
            ).order_by(Voice.version.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_version(self, character_id: uuid.UUID, version: int) -> Voice | None:
        result = await self.session.execute(
            select(Voice).where(
                Voice.character_id == character_id,
                Voice.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def set_selected(self, character_id: uuid.UUID, voice_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Voice).where(Voice.character_id == character_id).values(selected=False)
        )
        await self.session.execute(
            update(Voice).where(Voice.id == voice_id).values(selected=True)
        )
        await self.session.flush()
