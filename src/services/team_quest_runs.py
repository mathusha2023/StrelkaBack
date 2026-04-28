from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.achievements import AchievementCriteria
from src.models.quest_points import QuestPointModel
from src.models.quests import QuestModel, QuestStatus
from src.models.team_quest_runs import (
    TeamQuestRunCheckpointModel,
    TeamQuestRunModel,
    TeamQuestRunParticipantModel,
    TeamQuestRunStatus,
)
from src.models.teams import TeamModel
from src.models.users import UserModel
from src.schemes.auth import UserResponse
from src.schemes.team_quest_runs import (
    TeamQuestRunCheckpointAnswerResponse,
    TeamQuestRunCheckpointView,
    TeamQuestRunProgressResponse,
    TeamQuestRunStatusSchema,
)
from src.services.achievements import AchievementService
from src.services.quest_runs import _normalize_answer

TEAM_QUEST_START_DELAY_SECONDS = 5


def calculate_team_quest_completion_points(difficulty: int, elapsed_seconds: float) -> int:
    base = difficulty * 100
    speed_bonus = int((difficulty * 18000) / max(elapsed_seconds, 60.0))
    return max(1, base + speed_bonus)


class TeamQuestRunService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def update_readiness(
        self,
        current_user: UserResponse,
        quest_id: int,
        is_ready: bool,
    ) -> TeamQuestRunProgressResponse:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must be in a team to update team quest readiness",
            )

        quest = await self._get_quest_for_play(quest_id)
        team = await self._get_team(db_user.team_id)
        if is_ready and len(team.members) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team quest run requires at least two team members",
            )
        run = await self._get_active_run_for_team(team.id)
        if run is not None:
            run = await self._advance_start_if_ready(run)
        if run is not None and run.quest_id != quest.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Team already has an active team quest run for another quest",
            )

        if not is_ready:
            if run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active team quest run",
                )
            if run.status == TeamQuestRunStatus.IN_PROGRESS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Team quest run has already started",
                )
            await self._mark_participant_not_ready(run, db_user.id)
            self._cancel_scheduled_start(run)
            await self.session.commit()
            run = await self._get_run(run.id)
            return self._build_progress_response(run, team)

        if run is None:
            run = TeamQuestRunModel(
                team_id=team.id,
                quest_id=quest.id,
                status=TeamQuestRunStatus.WAITING_FOR_TEAM,
                starts_at=None,
                started_at=None,
                completed_at=None,
                points_awarded=None,
            )
            self.session.add(run)
            await self.session.flush()

        await self._mark_participant_ready(run, db_user.id)
        self._schedule_start_if_team_ready(run, team)
        await self.session.commit()
        run = await self._get_run(run.id)
        run = await self._advance_start_if_ready(run)
        return self._build_progress_response(run, team)

    async def get_active_run(self, current_user: UserResponse) -> TeamQuestRunProgressResponse:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must be in a team to have a team quest run",
            )

        team = await self._get_team(db_user.team_id)
        run = await self._get_active_run_for_team(team.id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active team quest run",
            )
        run = await self._advance_start_if_ready(run)
        return self._build_progress_response(run, team)

    async def submit_checkpoint_answer(
        self,
        current_user: UserResponse,
        checkpoint_id: int,
        answer: str,
    ) -> TeamQuestRunCheckpointAnswerResponse:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must be in a team to play a team quest",
            )

        team = await self._get_team(db_user.team_id)
        run = await self._get_active_run_for_team(team.id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active team quest run",
            )
        run = await self._advance_start_if_ready(run)
        if run.status != TeamQuestRunStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team quest run has not started yet",
            )

        point = self._get_point_from_run(run, checkpoint_id)
        if point is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Checkpoint not found in this quest",
            )
        if self._completed_checkpoint_by_point_id(run).get(point.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Checkpoint is already completed",
            )

        if _normalize_answer(answer) != _normalize_answer(point.correct_answer):
            return TeamQuestRunCheckpointAnswerResponse(
                correct=False,
                progress=self._build_progress_response(run, team),
                points_earned=None,
            )

        completed_at = datetime.now(timezone.utc)
        self.session.add(
            TeamQuestRunCheckpointModel(
                run_id=run.id,
                quest_point_id=point.id,
                completed_by_user_id=db_user.id,
                completed_at=completed_at,
            )
        )
        await self.session.flush()

        total_checkpoints = len(run.quest.points or [])
        completed_count = len(self._completed_checkpoint_by_point_id(run)) + 1
        points = None
        elapsed = None
        if completed_count >= total_checkpoints:
            elapsed = (completed_at - (run.started_at or completed_at)).total_seconds()
            if self._team_has_quest_creator(team, run.quest) or await self._has_completed_quest_before(run):
                points = 0
            else:
                points = calculate_team_quest_completion_points(
                    difficulty=run.quest.difficulty,
                    elapsed_seconds=elapsed,
                )
            run.status = TeamQuestRunStatus.COMPLETED
            run.completed_at = completed_at
            run.points_awarded = points
            if points > 0:
                await self._award_points_to_team_members(team, points)

        await self.session.commit()
        if points is not None and points > 0:
            achievement_service = AchievementService(self.session)
            for member in team.members:
                await achievement_service.award_eligible_achievements(member.id)
        if elapsed is not None and elapsed <= 60:
            achievement_service = AchievementService(self.session)
            for member in team.members:
                await achievement_service.award_achievement_by_criteria(
                    member.id,
                    AchievementCriteria.QUEST_UNDER_MINUTE,
                )
        run = await self._get_run(run.id)
        return TeamQuestRunCheckpointAnswerResponse(
            correct=True,
            progress=self._build_progress_response(run, team),
            points_earned=points,
        )

    async def _mark_participant_ready(self, run: TeamQuestRunModel, user_id: int) -> None:
        if any(participant.user_id == user_id for participant in run.participants):
            return
        self.session.add(
            TeamQuestRunParticipantModel(
                run=run,
                user_id=user_id,
                ready_at=datetime.now(timezone.utc),
            )
        )
        await self.session.flush()

    async def _mark_participant_not_ready(self, run: TeamQuestRunModel, user_id: int) -> None:
        participant = next(
            (participant for participant in run.participants if participant.user_id == user_id),
            None,
        )
        if participant is None:
            return
        await self.session.delete(participant)
        await self.session.flush()

    def _schedule_start_if_team_ready(self, run: TeamQuestRunModel, team: TeamModel) -> None:
        if run.status != TeamQuestRunStatus.WAITING_FOR_TEAM:
            return
        ready_member_ids = {participant.user_id for participant in run.participants}
        team_member_ids = {member.id for member in team.members}
        if team_member_ids and team_member_ids.issubset(ready_member_ids):
            now = datetime.now(timezone.utc)
            run.status = TeamQuestRunStatus.STARTING
            run.starts_at = now + timedelta(seconds=TEAM_QUEST_START_DELAY_SECONDS)

    @staticmethod
    def _cancel_scheduled_start(run: TeamQuestRunModel) -> None:
        if run.status == TeamQuestRunStatus.STARTING:
            run.status = TeamQuestRunStatus.WAITING_FOR_TEAM
            run.starts_at = None

    async def _advance_start_if_ready(self, run: TeamQuestRunModel) -> TeamQuestRunModel:
        if (
            run.status == TeamQuestRunStatus.STARTING
            and run.starts_at is not None
            and run.starts_at <= datetime.now(timezone.utc)
        ):
            run.status = TeamQuestRunStatus.IN_PROGRESS
            run.started_at = run.starts_at
            await self.session.commit()
            return await self._get_run(run.id)
        return run

    async def _award_points_to_team_members(self, team: TeamModel, points: int) -> None:
        for member in team.members:
            member.total_points += points

    @staticmethod
    def _team_has_quest_creator(team: TeamModel, quest: QuestModel) -> bool:
        return any(member.id == quest.creator_id for member in team.members)

    async def _has_completed_quest_before(self, run: TeamQuestRunModel) -> bool:
        result = await self.session.execute(
            select(TeamQuestRunModel.id).where(
                TeamQuestRunModel.team_id == run.team_id,
                TeamQuestRunModel.quest_id == run.quest_id,
                TeamQuestRunModel.status == TeamQuestRunStatus.COMPLETED,
                TeamQuestRunModel.id != run.id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _get_user(self, user_id: int) -> UserModel:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def _get_team(self, team_id: int) -> TeamModel:
        result = await self.session.execute(
            select(TeamModel).options(selectinload(TeamModel.members)).where(TeamModel.id == team_id)
        )
        team = result.scalar_one_or_none()
        if team is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )
        return team

    async def _get_quest_for_play(self, quest_id: int) -> QuestModel:
        result = await self.session.execute(
            select(QuestModel).options(selectinload(QuestModel.points)).where(QuestModel.id == quest_id)
        )
        quest = result.scalar_one_or_none()
        if quest is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")
        if quest.status != QuestStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only published quests can be played",
            )
        return quest

    async def _get_active_run_for_team(self, team_id: int) -> TeamQuestRunModel | None:
        result = await self.session.execute(
            select(TeamQuestRunModel)
            .options(
                selectinload(TeamQuestRunModel.quest).selectinload(QuestModel.points),
                selectinload(TeamQuestRunModel.participants),
                selectinload(TeamQuestRunModel.checkpoints),
            )
            .where(
                TeamQuestRunModel.team_id == team_id,
                TeamQuestRunModel.status.in_(
                    (
                        TeamQuestRunStatus.WAITING_FOR_TEAM,
                        TeamQuestRunStatus.STARTING,
                        TeamQuestRunStatus.IN_PROGRESS,
                    )
                ),
            )
        )
        return result.scalar_one_or_none()

    async def _get_run(self, run_id: int) -> TeamQuestRunModel:
        result = await self.session.execute(
            select(TeamQuestRunModel)
            .options(
                selectinload(TeamQuestRunModel.quest).selectinload(QuestModel.points),
                selectinload(TeamQuestRunModel.participants),
                selectinload(TeamQuestRunModel.checkpoints),
            )
            .where(TeamQuestRunModel.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team quest run not found",
            )
        return run

    @staticmethod
    def _completed_checkpoint_by_point_id(run: TeamQuestRunModel) -> dict[int, TeamQuestRunCheckpointModel]:
        return {checkpoint.quest_point_id: checkpoint for checkpoint in run.checkpoints}

    @staticmethod
    def _get_point_from_run(run: TeamQuestRunModel, checkpoint_id: int) -> QuestPointModel | None:
        for point in run.quest.points or []:
            if point.id == checkpoint_id:
                return point
        return None

    def _build_progress_response(self, run: TeamQuestRunModel, team: TeamModel) -> TeamQuestRunProgressResponse:
        completed_by_point_id = self._completed_checkpoint_by_point_id(run)
        sorted_points = sorted(run.quest.points or [], key=lambda p: p.id)
        checkpoints = [
            TeamQuestRunCheckpointView(
                id=point.id,
                title=point.title,
                latitude=point.latitude,
                longitude=point.longitude,
                task=point.task,
                hint=point.hint,
                point_rules=point.point_rules,
                is_completed=point.id in completed_by_point_id,
                completed_by_user_id=(
                    completed_by_point_id[point.id].completed_by_user_id
                    if point.id in completed_by_point_id
                    else None
                ),
                completed_at=(
                    completed_by_point_id[point.id].completed_at
                    if point.id in completed_by_point_id
                    else None
                ),
            )
            for point in sorted_points
        ]
        return TeamQuestRunProgressResponse(
            run_id=run.id,
            team_id=run.team_id,
            quest_id=run.quest_id,
            status=TeamQuestRunStatusSchema(run.status.value),
            ready_member_ids=sorted(participant.user_id for participant in run.participants),
            total_members=len(team.members),
            starts_at=run.starts_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            total_checkpoints=len(sorted_points),
            completed_checkpoints=len(completed_by_point_id),
            checkpoints=checkpoints,
            points_awarded=run.points_awarded,
        )
