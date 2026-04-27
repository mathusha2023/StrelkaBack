from asyncio import to_thread
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional
from uuid import uuid4

from minio import Minio
from minio.error import S3Error

from src.settings import settings


class MinioService:
    _client: Optional[Minio] = None

    @classmethod
    async def init_minio(cls) -> None:
        if cls._client is not None:
            return

        cls._client = Minio(
            endpoint=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        )
        bucket_exists = await to_thread(cls._client.bucket_exists, settings.s3_bucket)
        if not bucket_exists:
            await to_thread(cls._client.make_bucket, settings.s3_bucket)

    @classmethod
    async def close_minio(cls) -> None:
        cls._client = None

    @classmethod
    def _get_client(cls) -> Minio:
        if cls._client is None:
            raise RuntimeError("MinIO client is not initialized")
        return cls._client

    @classmethod
    async def upload_file(
        cls,
        object_name: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        client = cls._get_client()
        stream, length = await cls._prepare_stream(data)
        await to_thread(
            client.put_object,
            settings.s3_bucket,
            object_name,
            stream,
            length,
            content_type=content_type,
        )
        return object_name

    @classmethod
    async def upload_file_with_uuid(
        cls,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        original_filename: str | None = None,
    ) -> str:
        extension = Path(original_filename or "").suffix
        object_name = f"{uuid4()}{extension}"
        return await cls.upload_file(object_name, data, content_type=content_type)

    @classmethod
    async def delete_file(cls, object_name: str) -> None:
        client = cls._get_client()
        try:
            await to_thread(client.remove_object, settings.s3_bucket, object_name)
        except S3Error as exc:
            if exc.code != "NoSuchKey":
                raise

    @classmethod
    async def get_file_stream(cls, object_name: str) -> tuple[BytesIO, str]:
        client = cls._get_client()
        response = await to_thread(client.get_object, settings.s3_bucket, object_name)
        try:
            payload = await to_thread(response.read)
            content_type = response.headers.get("Content-Type", "application/octet-stream")
        finally:
            await to_thread(response.close)
            await to_thread(response.release_conn)
        return BytesIO(payload), content_type

    @staticmethod
    async def _prepare_stream(data: bytes | BinaryIO) -> tuple[BinaryIO, int]:
        if isinstance(data, bytes):
            return BytesIO(data), len(data)

        await to_thread(data.seek, 0)
        payload = await to_thread(data.read)
        if isinstance(payload, str):
            payload = payload.encode()
        return BytesIO(payload), len(payload)
