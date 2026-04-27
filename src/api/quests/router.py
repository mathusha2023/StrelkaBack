from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.quests import QuestCreate, QuestListFilters, QuestPageResponse, QuestResponse
from src.services.auth import get_current_user
from src.services.quests import QuestService

router = APIRouter(tags=["Quests"], prefix="/quests")


@router.post("", response_model=QuestResponse, status_code=status.HTTP_201_CREATED)
async def create_quest(
    payload: QuestCreate = Depends(QuestCreate.as_form),
    image: UploadFile | None = File(default=None),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).create_quest(current_user, payload, image)


@router.get("", response_model=QuestPageResponse)
async def get_all_quests(
    filters: QuestListFilters = Depends(QuestListFilters.as_query),
    session: AsyncSession = Depends(create_session),
) -> QuestPageResponse:
    return await QuestService(session).get_all_quests(filters)


@router.get("/my", response_model=QuestPageResponse)
async def get_my_quests(
    filters: QuestListFilters = Depends(QuestListFilters.as_query),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestPageResponse:
    return await QuestService(session).get_my_quests(current_user, filters)


@router.get("/{quest_id}", response_model=QuestResponse)
async def get_quest(
    quest_id: int,
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).get_quest(quest_id)
