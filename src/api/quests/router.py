from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.quests import (
    QuestArchiveStatusUpdateRequest,
    QuestComplaintCreateRequest,
    QuestComplaintResponse,
    QuestCreate,
    QuestListFilters,
    QuestPageResponse,
    QuestResponse,
)
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


@router.patch("/{quest_id}/status", response_model=QuestResponse)
async def update_my_quest_status(
    quest_id: int,
    payload: QuestArchiveStatusUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).update_my_quest_archive_status(
        current_user=current_user,
        quest_id=quest_id,
        target_status=payload.status,
    )


@router.delete("/{quest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_quest(
    quest_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> None:
    await QuestService(session).delete_my_quest(current_user, quest_id)


@router.post("/{quest_id}/complaints", response_model=QuestComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_quest_complaint(
    quest_id: int,
    payload: QuestComplaintCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestComplaintResponse:
    return await QuestService(session).create_complaint(current_user, quest_id, payload)
