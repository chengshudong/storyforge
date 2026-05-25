import redis.asyncio as aioredis

from infra.config import settings

redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def check_redis_health() -> bool:
    try:
        client = await get_redis()
        await client.ping()
        return True
    except Exception:
        return False
