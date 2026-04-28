from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.quest_runs import (
    QuestRunAnswerRequest,
    QuestRunAnswerResponse,
    QuestRunHistoryItem,
    QuestRunProgressResponse,
    QuestRunStartRequest,
)
from src.services.auth import get_current_user
from src.services.quest_runs import QuestRunService

router = APIRouter(tags=["Quest Runs"], prefix="/quest-runs")


@router.get("/active", response_model=QuestRunProgressResponse)
async def get_active_quest_run(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestRunProgressResponse:
    return await QuestRunService(session).get_active_run(current_user)


@router.post("/active/answer", response_model=QuestRunAnswerResponse)
async def submit_active_quest_run_answer(
    payload: QuestRunAnswerRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestRunAnswerResponse:
    return await QuestRunService(session).submit_answer_for_active_run(
        current_user, payload.answer
    )


@router.post("/active/abandon", response_model=QuestRunProgressResponse)
async def abandon_active_quest_run(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestRunProgressResponse:
    return await QuestRunService(session).abandon_active_run(current_user)


@router.post(
    "",
    response_model=QuestRunProgressResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_quest_run(
    payload: QuestRunStartRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestRunProgressResponse:
    return await QuestRunService(session).start_run(current_user, payload.quest_id)


@router.get("/history", response_model=list[QuestRunHistoryItem])
async def get_quest_runs_history(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> list[QuestRunHistoryItem]:
    return await QuestRunService(session).list_history_runs(current_user)
