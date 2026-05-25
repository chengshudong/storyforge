import pytest

pytest.importorskip("redis")


def test_redis_url_format():
    from infra.config import settings
    url = settings.redis_url
    assert url.startswith("redis://")


async def test_redis_client_created():
    from infra.redis import get_redis
    client = await get_redis()
    assert client is not None
