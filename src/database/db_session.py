import logging
from typing import Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from src.database.base import Base
import src.models  # ensure all models are imported for table creation


class AsyncPostgresClient:
    _engine: Optional[AsyncEngine] = None
    _async_session_maker: Optional[async_sessionmaker] = None

    @classmethod
    async def init_postgres(cls, db_url: str) -> None:
        if cls._async_session_maker is not None:
            logging.warning("Postgres is already initialized")
            return

        cls._engine = create_async_engine(db_url, max_overflow=1100, pool_size=1000, echo=True)
        cls._async_session_maker = async_sessionmaker(bind=cls._engine, expire_on_commit=False)

        async with cls._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logging.info("Postgres initialized")

    @classmethod
    async def close_postgres(cls) -> None:
        if cls._engine is not None:
            logging.info("Postgres closed")
            await cls._engine.dispose()
            cls._engine = None
            cls._async_session_maker = None

    @classmethod
    def get_async_session(cls) -> async_sessionmaker:
        return cls._async_session_maker


async def create_session() -> AsyncGenerator[AsyncSession, None]:
    async_session_maker = AsyncPostgresClient.get_async_session()
    async with async_session_maker() as session:
        yield session