import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from src.api import main_router
from src.database.db_session import AsyncPostgresClient
from src.database.redis_session import RedisClient
from src.services.minio import MinioService
from src.settings import settings


class App(FastAPI):
    def __init__(self):
        super().__init__(title="Strelka", lifespan=App.lifespan, debug=True)
        super().include_router(main_router)
        super().add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @staticmethod
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await AsyncPostgresClient.init_postgres(settings.postgres_url)
        await RedisClient.init_redis(settings.redis_url)
        await MinioService.init_minio()
        logging.info("All resources have been successfully initialized")

        yield

        await MinioService.close_minio()
        await RedisClient.close_redis()
        await AsyncPostgresClient.close_postgres()
        logging.info("All resources have been successfully closed")
