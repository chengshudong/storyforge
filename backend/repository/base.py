import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: uuid.UUID) -> T | None:
        return await self.session.get(self.model, id)

    async def list(self, offset: int = 0, limit: int = 100) -> list[T]:
        result = await self.session.execute(
            select(self.model).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def update(self, entity: T) -> T:
        await self.session.merge(entity)
        await self.session.flush()
        return entity

    async def delete(self, id: uuid.UUID) -> bool:
        entity = await self.get(id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return result.scalar_one()
