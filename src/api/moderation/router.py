from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.quests import (
    QuestComplaintPageResponse,
    QuestListFilters,
    QuestPageResponse,
    QuestRejectRequest,
    QuestResponse,
)
from src.services.auth import require_moderator
from src.services.quests import QuestService

router = APIRouter(tags=["Moderation"], prefix="/moderation")


@router.get("/quests", response_model=QuestPageResponse)
async def get_quests_on_moderation(
    filters: QuestListFilters = Depends(QuestListFilters.as_query),
    _: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> QuestPageResponse:
    return await QuestService(session).get_quests_on_moderation(filters)


@router.post("/quests/{quest_id}/publish", response_model=QuestResponse)
async def publish_quest(
    quest_id: int,
    _: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).publish_quest(quest_id)


@router.post("/quests/{quest_id}/reject", response_model=QuestResponse)
async def reject_quest(
    quest_id: int,
    payload: QuestRejectRequest,
    _: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).reject_quest(quest_id, payload.reason)


@router.delete("/quests/{quest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quest_as_moderator(
    quest_id: int,
    _: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> None:
    await QuestService(session).delete_quest_as_moderator(quest_id)


@router.get("/complaints", response_model=QuestComplaintPageResponse)
async def get_all_complaints(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> QuestComplaintPageResponse:
    return await QuestService(session).get_all_complaints(limit=limit, offset=offset)


@router.delete("/complaints/{complaint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_complaint(
    complaint_id: int,
    _: UserResponse = Depends(require_moderator),
    session: AsyncSession = Depends(create_session),
) -> None:
    await QuestService(session).delete_complaint(complaint_id)
