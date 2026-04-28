from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.team_quest_runs import (
    TeamQuestRunCheckpointAnswerRequest,
    TeamQuestRunCheckpointAnswerResponse,
    TeamQuestRunProgressResponse,
    TeamQuestRunReadinessRequest,
)
from src.services.auth import get_current_user
from src.services.team_quest_runs import TeamQuestRunService

router = APIRouter(tags=["Team Quest Runs"], prefix="/team-quest-runs")


@router.patch("", response_model=TeamQuestRunProgressResponse | None)
async def update_team_quest_run_readiness(
    payload: TeamQuestRunReadinessRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamQuestRunProgressResponse | None:
    return await TeamQuestRunService(session).update_readiness(
        current_user=current_user,
        quest_id=payload.quest_id,
        is_ready=payload.is_ready,
    )


@router.get("/active", response_model=TeamQuestRunProgressResponse)
async def get_active_team_quest_run(
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamQuestRunProgressResponse:
    return await TeamQuestRunService(session).get_active_run(current_user)


@router.post("/active/checkpoints/{checkpoint_id}/answer", response_model=TeamQuestRunCheckpointAnswerResponse)
async def submit_team_quest_checkpoint_answer(
    checkpoint_id: int,
    payload: TeamQuestRunCheckpointAnswerRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> TeamQuestRunCheckpointAnswerResponse:
    return await TeamQuestRunService(session).submit_checkpoint_answer(
        current_user=current_user,
        checkpoint_id=checkpoint_id,
        answer=payload.answer,
    )
