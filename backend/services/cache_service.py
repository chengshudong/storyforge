from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from infra.redis import get_redis

logger = logging.getLogger(__name__)

CACHE_DB = 2  # Dedicated Redis DB index per MODEL_POLICY §5


class CacheService:
    """Redis-backed model response cache per MODEL_POLICY §5."""

    async def _client(self):
        client = await get_redis()
        return client

    def build_key(self, entity: str, project_id: str, content_hash: str) -> str:
        return f"cache:model:{entity}:{project_id}:{content_hash}"

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:16]

    async def get(self, key: str) -> dict | None:
        try:
            client = await self._client()
            raw = await client.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("cache get failed: %s", e)
        return None

    async def set(self, key: str, value: dict, ttl: int) -> None:
        try:
            client = await self._client()
            await client.set(key, json.dumps(value), ex=ttl)
        except Exception as e:
            logger.warning("cache set failed: %s", e)

    async def invalidate_project(self, project_id: str) -> int:
        try:
            client = await self._client()
            pattern = f"cache:model:*:{project_id}:*"
            keys = []
            async for k in client.scan_iter(match=pattern):
                keys.append(k)
            if keys:
                await client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.warning("cache invalidate failed: %s", e)
            return 0
