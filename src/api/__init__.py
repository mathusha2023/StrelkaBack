from fastapi import APIRouter
from src.api.auth import router as auth_router

main_router = APIRouter(prefix="/api")


@main_router.get("/health_check", summary="Health check", tags=["Health check"])
async def health_check() -> dict:
    return {"status": "ok"}


main_router.include_router(auth_router)
