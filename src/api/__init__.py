from fastapi import APIRouter
from src.api.auth import router as auth_router
from src.api.common import router as common_router
from src.api.moderation import router as moderation_router
from src.api.quests import router as quests_router
from src.api.teams import router as teams_router

main_router = APIRouter(prefix="/api")


@main_router.get("/health_check", summary="Health check", tags=["Health check"])
async def health_check() -> dict:
    return {"status": "ok"}


main_router.include_router(common_router)
main_router.include_router(auth_router)
main_router.include_router(teams_router)
main_router.include_router(quests_router)
main_router.include_router(moderation_router)
