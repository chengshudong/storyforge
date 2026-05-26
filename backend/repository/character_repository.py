import uuid

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from domain.models import Character, CharacterVersion
from repository.base import BaseRepository


class CharacterRepository(BaseRepository[Character]):
    model = Character

    async def list_by_project(self, project_id: uuid.UUID, offset: int = 0, limit: int = 100,
                              role: str | None = None, locked: bool | None = None) -> list[Character]:
        stmt = select(Character).where(Character.project_id == project_id)
        if role is not None:
            stmt = stmt.where(Character.role == role)
        if locked is not None:
            stmt = stmt.where(Character.locked == locked)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(self, project_id: uuid.UUID,
                               role: str | None = None, locked: bool | None = None) -> int:
        stmt = select(func.count()).select_from(Character).where(Character.project_id == project_id)
        if role is not None:
            stmt = stmt.where(Character.role == role)
        if locked is not None:
            stmt = stmt.where(Character.locked == locked)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_by_name(self, project_id: uuid.UUID, name: str) -> Character | None:
        result = await self.session.execute(
            select(Character).where(
                Character.project_id == project_id,
                Character.name == name,
            )
        )
        return result.scalar_one_or_none()

    # ── Version management ───────────────────────────────────────────────

    async def create_version(self, character_id: uuid.UUID, version_number: int,
                             profile_snapshot: dict, diff: dict | None = None,
                             created_by: str | None = None) -> CharacterVersion:
        version = CharacterVersion(
            character_id=character_id,
            version_number=version_number,
            profile_snapshot=profile_snapshot,
            diff=diff,
            created_by=created_by,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def list_versions(self, character_id: uuid.UUID) -> list[CharacterVersion]:
        result = await self.session.execute(
            select(CharacterVersion)
            .where(CharacterVersion.character_id == character_id)
            .order_by(desc(CharacterVersion.version_number))
        )
        return list(result.scalars().all())

    async def get_version(self, character_id: uuid.UUID, version_number: int) -> CharacterVersion | None:
        result = await self.session.execute(
            select(CharacterVersion).where(
                CharacterVersion.character_id == character_id,
                CharacterVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_version_number(self, character_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.max(CharacterVersion.version_number))
            .where(CharacterVersion.character_id == character_id)
        )
        return result.scalar_one() or 0
