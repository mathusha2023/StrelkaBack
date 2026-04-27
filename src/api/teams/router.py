from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.teams import TeamCreate, TeamJoinRequest, TeamResponse
from src.services.auth import get_current_user
from src.services.teams import TeamService

router = APIRouter(tags=["Teams"], prefix="/teams")


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamResponse:
    return await TeamService(session).create_team(current_user, payload)


@router.get("/me", response_model=TeamResponse)
async def get_my_team(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamResponse:
    return await TeamService(session).get_my_team(current_user)


@router.post("/join", response_model=TeamResponse)
async def join_team(
    payload: TeamJoinRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamResponse:
    return await TeamService(session).join_team(current_user, payload.code)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> Response:
    await TeamService(session).leave_team(current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/members/{member_id}", response_model=TeamResponse)
async def kick_member(
    member_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamResponse:
    return await TeamService(session).kick_member(current_user, member_id)
