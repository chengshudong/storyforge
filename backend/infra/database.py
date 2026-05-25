from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from infra.config import settings

_engine = None
_async_session_factory = None


class Base(DeclarativeBase):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url, echo=settings.debug, pool_size=10, max_overflow=20
        )
    return _engine


def _get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def get_db() -> AsyncSession:
    async with _get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def check_database_health() -> bool:
    from sqlalchemy import text
    try:
        async with _get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True
    except Exception:
        return False
