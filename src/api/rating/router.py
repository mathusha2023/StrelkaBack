from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.rating import RatingFilters, TeamRatingPageResponse, UserRatingPageResponse
from src.services.auth import get_current_user
from src.services.rating import RatingService

router = APIRouter(tags=["Rating"], prefix="/rating")


@router.get("/users", response_model=UserRatingPageResponse)
async def get_users_rating(
    filters: RatingFilters = Depends(RatingFilters.as_query),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> UserRatingPageResponse:
    return await RatingService(session).get_users_rating(current_user, filters)


@router.get("/teams", response_model=TeamRatingPageResponse)
async def get_teams_rating(
    filters: RatingFilters = Depends(RatingFilters.as_query),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamRatingPageResponse:
    return await RatingService(session).get_teams_rating(current_user, filters)
