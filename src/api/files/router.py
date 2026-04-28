from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from minio.error import S3Error

from src.services.minio import MinioService

router = APIRouter(tags=["Files"])


@router.get("/file/{file_id}")
async def get_file(file_id: str) -> StreamingResponse:
    try:
        stream, content_type = await MinioService.get_file_stream(file_id)
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            raise HTTPException(status_code=404, detail="File not found") from None
        raise

    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{file_id}"'},
    )
