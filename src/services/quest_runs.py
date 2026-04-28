from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.achievements import AchievementCriteria
from src.models.quest_points import QuestPointModel
from src.models.quest_runs import QuestRunModel, QuestRunStatus
from src.models.quests import QuestModel, QuestStatus
from src.models.users import UserModel
from src.schemes.auth import UserResponse
from src.schemes.quest_runs import (
    CheckpointCurrentView,
    CheckpointPassedView,
    QuestRunAnswerResponse,
    QuestRunHistoryItem,
    QuestRunProgressResponse,
    QuestRunStatusSchema,
)
from src.services.achievements import AchievementService


_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")


def _normalize_answer(value: str) -> str:
    """Same semantic matching logic as quest text search: yo/e, punctuation, whitespace."""
    value = unicodedata.normalize("NFKC", value)
    value = _ZERO_WIDTH_RE.sub("", value)
    value = value.casefold().strip()
    value = value.replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def calculate_quest_completion_points(difficulty: int, duration_minutes: int, elapsed_seconds: float) -> int:
    """Base points plus a speed bonus relative to the declared quest duration."""
    base = difficulty * 80
    expected_sec = max(float(duration_minutes) * 60.0, 60.0)
    elapsed_seconds = max(elapsed_seconds, 1.0)
    if elapsed_seconds <= expected_sec:
        ratio = (expected_sec - elapsed_seconds) / expected_sec
        speed_bonus = int(ratio * 50 * difficulty)
    else:
        overtime_ratio = min((elapsed_seconds - expected_sec) / expected_sec, 2.0)
        speed_bonus = -int(overtime_ratio * 30 * difficulty)
    return max(1, base + speed_bonus)


class QuestRunService:
    """A user can have at most one active run at a time (for any quest)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def start_run(self, current_user: UserResponse, quest_id: int) -> QuestRunProgressResponse:
        quest = await self._get_quest_for_play(quest_id)
        active = await self._get_any_in_progress_run(current_user.id)
        if active is not None:
            if active.quest_id == quest_id:
                full = await self._get_run_with_quest(active.id, current_user.id)
                return self._build_progress_response(full, full.quest)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active quest; finish it before starting another one",
            )

        now = datetime.now(timezone.utc)
        run = QuestRunModel(
            user_id=current_user.id,
            quest_id=quest_id,
            status=QuestRunStatus.IN_PROGRESS,
            started_at=now,
            completed_at=None,
            current_step_index=0,
            points_awarded=None,
        )
        self.session.add(run)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active quest; finish it before starting another one",
            ) from None
        await self.session.refresh(run)
        run_loaded = await self._get_run_with_quest(run.id, current_user.id)
        return self._build_progress_response(run_loaded, run_loaded.quest)

    async def get_active_run(self, current_user: UserResponse) -> QuestRunProgressResponse:
        """The user's single active run (if any)."""
        run = await self._get_any_in_progress_run(current_user.id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active quest run",
            )
        run = await self._get_run_with_quest(run.id, current_user.id)
        return self._build_progress_response(run, run.quest)

    async def submit_answer_for_active_run(
        self,
        current_user: UserResponse,
        answer: str,
    ) -> QuestRunAnswerResponse:
        active = await self._get_any_in_progress_run(current_user.id)
        if active is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active quest run",
            )
        return await self.submit_answer(current_user, active.quest_id, active.id, answer)

    async def abandon_active_run(self, current_user: UserResponse) -> QuestRunProgressResponse:
        run = await self._get_any_in_progress_run(current_user.id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active quest run",
            )
        run = await self._get_run_with_quest(run.id, current_user.id)
        run.status = QuestRunStatus.ABANDONED
        run.completed_at = datetime.now(timezone.utc)
        run.points_awarded = 0
        await self.session.commit()
        await self.session.refresh(run)
        run = await self._get_run_with_quest(run.id, current_user.id)
        return self._build_progress_response(run, run.quest)

    async def list_history_runs(self, current_user: UserResponse) -> list[QuestRunHistoryItem]:
        result = await self.session.execute(
            select(QuestRunModel)
            .options(selectinload(QuestRunModel.quest))
            .where(
                QuestRunModel.user_id == current_user.id,
                QuestRunModel.status.in_((QuestRunStatus.COMPLETED, QuestRunStatus.ABANDONED)),
            )
            .order_by(QuestRunModel.started_at.desc())
        )
        runs = result.scalars().all()
        items: list[QuestRunHistoryItem] = []
        for run in runs:
            quest = run.quest
            completed_at = run.completed_at if run.completed_at is not None else run.started_at
            items.append(
                QuestRunHistoryItem(
                    run_id=run.id,
                    quest_id=run.quest_id,
                    quest_title=quest.title if quest is not None else "",
                    status=QuestRunStatusSchema(run.status.value),
                    started_at=run.started_at,
                    completed_at=completed_at,
                    points_awarded=run.points_awarded if run.points_awarded is not None else 0,
                )
            )
        return items

    async def submit_answer(
        self,
        current_user: UserResponse,
        quest_id: int,
        run_id: int,
        answer: str,
    ) -> QuestRunAnswerResponse:
        run = await self._get_run_with_quest(run_id, current_user.id)
        if run.quest_id != quest_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest run not found",
            )
        quest = run.quest
        if run.status != QuestRunStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quest run is already finished",
            )

        sorted_points = self._sorted_points(quest)
        if not sorted_points:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Quest has no checkpoints",
            )

        idx = run.current_step_index
        if idx < 0 or idx >= len(sorted_points):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid run state",
            )

        current_point = sorted_points[idx]
        ok = _normalize_answer(answer) == _normalize_answer(current_point.correct_answer)
        if not ok:
            return QuestRunAnswerResponse(
                correct=False,
                progress=self._build_progress_response(run, quest),
                points_earned=None,
            )

        if idx == len(sorted_points) - 1:
            completed_at = datetime.now(timezone.utc)
            elapsed = (completed_at - run.started_at).total_seconds()
            own_quest = quest.creator_id == current_user.id
            has_non_rewardable_before = await self._has_non_rewardable_run_before(
                user_id=current_user.id,
                quest_id=quest.id,
                current_run_id=run.id,
            )
            if own_quest or has_non_rewardable_before:
                points = 0
            else:
                points = calculate_quest_completion_points(
                    difficulty=quest.difficulty,
                    duration_minutes=quest.duration_minutes,
                    elapsed_seconds=elapsed,
                )
            run.status = QuestRunStatus.COMPLETED
            run.completed_at = completed_at
            run.current_step_index = len(sorted_points)
            run.points_awarded = points

            if points > 0:
                user_result = await self.session.execute(select(UserModel).where(UserModel.id == current_user.id))
                user = user_result.scalar_one()
                user.total_points += points

            await self.session.commit()
            achievement_service = AchievementService(self.session)
            if points > 0:
                await achievement_service.award_eligible_achievements(current_user.id)
            if elapsed <= 60:
                await achievement_service.award_achievement_by_criteria(
                    current_user.id,
                    AchievementCriteria.QUEST_UNDER_MINUTE,
                )
            await self.session.refresh(run)
            run = await self._get_run_with_quest(run.id, current_user.id)
            progress = self._build_progress_response(run, run.quest)
            return QuestRunAnswerResponse(correct=True, progress=progress, points_earned=points)

        run.current_step_index = idx + 1
        await self.session.commit()
        await self.session.refresh(run)
        run = await self._get_run_with_quest(run.id, current_user.id)
        progress = self._build_progress_response(run, run.quest)
        return QuestRunAnswerResponse(correct=True, progress=progress, points_earned=None)

    async def _get_quest_for_play(self, quest_id: int) -> QuestModel:
        result = await self.session.execute(
            select(QuestModel)
            .options(selectinload(QuestModel.points))
            .where(QuestModel.id == quest_id)
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

    async def _get_any_in_progress_run(self, user_id: int) -> QuestRunModel | None:
        result = await self.session.execute(
            select(QuestRunModel).where(
                QuestRunModel.user_id == user_id,
                QuestRunModel.status == QuestRunStatus.IN_PROGRESS,
            )
        )
        return result.scalar_one_or_none()

    async def _get_run_with_quest(self, run_id: int, user_id: int) -> QuestRunModel:
        result = await self.session.execute(
            select(QuestRunModel)
            .options(selectinload(QuestRunModel.quest).selectinload(QuestModel.points))
            .where(QuestRunModel.id == run_id, QuestRunModel.user_id == user_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest run not found")
        return run

    async def _has_non_rewardable_run_before(self, user_id: int, quest_id: int, current_run_id: int) -> bool:
        result = await self.session.execute(
            select(QuestRunModel.id)
            .where(
                QuestRunModel.user_id == user_id,
                QuestRunModel.quest_id == quest_id,
                QuestRunModel.status.in_((QuestRunStatus.COMPLETED, QuestRunStatus.ABANDONED)),
                QuestRunModel.id != current_run_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _sorted_points(quest: QuestModel) -> list[QuestPointModel]:
        return sorted(quest.points or [], key=lambda p: p.id)

    def _build_progress_response(self, run: QuestRunModel, quest: QuestModel) -> QuestRunProgressResponse:
        sorted_points = self._sorted_points(quest)
        total = len(sorted_points)
        status_schema = QuestRunStatusSchema(run.status.value)

        if run.status in (QuestRunStatus.COMPLETED, QuestRunStatus.ABANDONED):
            previous = [
                CheckpointPassedView.model_validate(p)
                for p in sorted_points[:min(run.current_step_index, total)]
            ]
            return QuestRunProgressResponse(
                run_id=run.id,
                quest_id=quest.id,
                status=status_schema,
                started_at=run.started_at,
                completed_at=run.completed_at,
                total_checkpoints=total,
                current_step_index=min(run.current_step_index, total),
                previous_checkpoints=previous,
                current_checkpoint=None,
                points_awarded=run.points_awarded,
            )

        idx = run.current_step_index
        if idx < 0 or idx >= total:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid quest run progress state",
            )

        previous = [CheckpointPassedView.model_validate(p) for p in sorted_points[:idx]]
        current = sorted_points[idx]
        current_view = CheckpointCurrentView(
            id=current.id,
            title=current.title,
            latitude=current.latitude,
            longitude=current.longitude,
            task=current.task,
            hint=current.hint,
            point_rules=current.point_rules,
        )

        return QuestRunProgressResponse(
            run_id=run.id,
            quest_id=quest.id,
            status=status_schema,
            started_at=run.started_at,
            completed_at=None,
            total_checkpoints=total,
            current_step_index=idx,
            previous_checkpoints=previous,
            current_checkpoint=current_view,
            points_awarded=None,
        )
