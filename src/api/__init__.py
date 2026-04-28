from fastapi import APIRouter
from src.api.achievements import router as achievements_router
from src.api.auth import router as auth_router
from src.api.files import router as files_router
from src.api.moderation import router as moderation_router
from src.api.quest_runs import router as quest_runs_router
from src.api.quests import router as quests_router
from src.api.rating import router as rating_router
from src.api.team_quest_runs import router as team_quest_runs_router
from src.api.teams import router as teams_router

main_router = APIRouter(prefix="/api")


@main_router.get("/health_check", summary="Health check", tags=["Health check"])
async def health_check() -> dict:
    return {"status": "ok"}


main_router.include_router(files_router)
main_router.include_router(auth_router)
main_router.include_router(achievements_router)
main_router.include_router(teams_router)
main_router.include_router(quests_router)
main_router.include_router(quest_runs_router)
main_router.include_router(team_quest_runs_router)
main_router.include_router(rating_router)
main_router.include_router(moderation_router)
