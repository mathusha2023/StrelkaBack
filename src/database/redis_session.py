import logging
from typing import Optional

from redis.asyncio import Redis


class RedisClient:
    _client: Optional[Redis] = None

    @classmethod
    async def init_redis(cls, redis_url: str) -> None:
        if cls._client is not None:
            logging.warning("Redis is already initialized")
            return

        cls._client = Redis.from_url(redis_url, decode_responses=True)
        await cls._client.ping()
        logging.info("Redis initialized")

    @classmethod
    async def close_redis(cls) -> None:
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None
            logging.info("Redis closed")

    @classmethod
    def get_client(cls) -> Redis:
        if cls._client is None:
            raise RuntimeError("Redis is not initialized")
        return cls._client
