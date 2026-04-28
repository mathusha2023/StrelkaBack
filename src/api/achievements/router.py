from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.achievements import (
    AchievementFilters,
    AchievementPageResponse,
    AchievementResponse,
    UserAchievementPageResponse,
)
from src.schemes.auth import UserResponse
from src.services.achievements import AchievementService
from src.services.auth import get_current_user, require_moderator

router = APIRouter(tags=["Achievements"], prefix="/achievements")


@router.get("", response_model=AchievementPageResponse)
async def get_all_achievements(
    filters: AchievementFilters = Depends(AchievementFilters.as_query),
    session: AsyncSession = Depends(create_session),
) -> AchievementPageResponse:
    return await AchievementService(session).list_all_achievements(filters)


@router.get("/me", response_model=UserAchievementPageResponse)
async def get_my_achievements(
    filters: AchievementFilters = Depends(AchievementFilters.as_query),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> UserAchievementPageResponse:
    return await AchievementService(session).list_my_achievements(current_user, filters)


@router.post("/{achievement_id}/image", response_model=AchievementResponse)
async def upload_achievement_image(
    achievement_id: int,
    image: UploadFile = File(...),
    _moderator: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> AchievementResponse:
    return await AchievementService(session).upload_achievement_image(achievement_id, image)
