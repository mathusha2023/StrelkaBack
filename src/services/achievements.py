import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.achievements import AchievementCriteria, AchievementModel, UserAchievementModel
from src.models.teams import TeamModel
from src.models.users import UserModel, UserRole
from src.schemes.achievements import (
    AchievementFilters,
    AchievementPageResponse,
    AchievementResponse,
    UserAchievementPageResponse,
    UserAchievementResponse,
)
from src.schemes.auth import UserResponse
from src.services.minio import MinioService

ACHIEVEMENTS_FILE = Path(__file__).resolve().parents[1] / "data" / "achievements.json"


def load_default_achievements() -> list[dict]:
    with ACHIEVEMENTS_FILE.open(encoding="utf-8") as file:
        achievements = json.load(file)
    return [
        {
            **achievement,
            "criteria": AchievementCriteria(achievement["criteria"]),
        }
        for achievement in achievements
    ]


class AchievementService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all_achievements(self, filters: AchievementFilters) -> AchievementPageResponse:
        await self._ensure_default_achievements()
        total_result = await self.session.execute(select(func.count(AchievementModel.id)))
        total = int(total_result.scalar_one())
        result = await self.session.execute(
            select(AchievementModel)
            .order_by(AchievementModel.id)
            .offset(filters.offset)
            .limit(filters.limit)
        )
        return AchievementPageResponse(
            items=[AchievementResponse.model_validate(achievement) for achievement in result.scalars().all()],
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    async def list_my_achievements(
        self,
        current_user: UserResponse,
        filters: AchievementFilters,
    ) -> UserAchievementPageResponse:
        return await self._list_user_achievements(current_user.id, filters)

    async def _list_user_achievements(
        self,
        user_id: int,
        filters: AchievementFilters,
    ) -> UserAchievementPageResponse:
        await self._deduplicate_user_achievements(user_id)
        await self.award_eligible_achievements(user_id)
        total_result = await self.session.execute(
            select(func.count(UserAchievementModel.id)).where(UserAchievementModel.user_id == user_id)
        )
        total = int(total_result.scalar_one())
        result = await self.session.execute(
            select(UserAchievementModel)
            .options(selectinload(UserAchievementModel.achievement))
            .where(UserAchievementModel.user_id == user_id)
            .order_by(UserAchievementModel.awarded_at.desc(), UserAchievementModel.id.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        )
        return UserAchievementPageResponse(
            items=[
                UserAchievementResponse(
                    **AchievementResponse.model_validate(user_achievement.achievement).model_dump(),
                    awarded_at=user_achievement.awarded_at,
                )
                for user_achievement in result.scalars().all()
            ],
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    async def upload_achievement_image(self, achievement_id: int, image: UploadFile) -> AchievementResponse:
        achievement = await self._get_achievement(achievement_id)
        image_file_id = await MinioService.upload_file_with_uuid(
            data=image.file,
            content_type=image.content_type or "application/octet-stream",
            original_filename=image.filename,
        )
        achievement.image_file_id = image_file_id
        await self.session.commit()
        await self.session.refresh(achievement)
        return AchievementResponse.model_validate(achievement)

    async def award_eligible_achievements(self, user_id: int) -> None:
        await self._ensure_default_achievements()
        await self._deduplicate_user_achievements(user_id)
        user = await self._get_user(user_id)
        achievements_result = await self.session.execute(select(AchievementModel))
        achievements = achievements_result.scalars().all()

        awarded_result = await self.session.execute(
            select(UserAchievementModel.achievement_id).where(UserAchievementModel.user_id == user_id)
        )
        awarded_ids = set(awarded_result.scalars().all())

        user_place = await self._get_user_rating_place(user)
        team_place = await self._get_user_team_rating_place(user)
        now = datetime.now(timezone.utc)
        changed = False
        for achievement in achievements:
            if achievement.id in awarded_ids:
                continue
            if not self._matches_achievement(user, achievement, user_place, team_place):
                continue
            self._add_user_achievement(user.id, achievement.id, now)
            awarded_ids.add(achievement.id)
            changed = True

        if changed:
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()

    async def award_achievement_by_criteria(self, user_id: int, criteria: AchievementCriteria) -> None:
        await self._ensure_default_achievements()
        await self._deduplicate_user_achievements(user_id)
        user = await self._get_user(user_id)
        result = await self.session.execute(
            select(AchievementModel).where(
                AchievementModel.criteria == criteria,
                AchievementModel.points_required.is_(None),
            )
        )
        achievement = result.scalar_one_or_none()
        if achievement is None:
            return

        awarded_result = await self.session.execute(
            select(UserAchievementModel.id).where(
                UserAchievementModel.user_id == user.id,
                UserAchievementModel.achievement_id == achievement.id,
            )
        )
        if awarded_result.scalar_one_or_none() is not None:
            return

        self._add_user_achievement(user.id, achievement.id, datetime.now(timezone.utc))
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()

    async def _deduplicate_user_achievements(self, user_id: int) -> None:
        result = await self.session.execute(
            select(UserAchievementModel)
            .where(UserAchievementModel.user_id == user_id)
            .order_by(
                UserAchievementModel.achievement_id,
                UserAchievementModel.awarded_at.asc(),
                UserAchievementModel.id.asc(),
            )
        )
        seen_achievement_ids: set[int] = set()
        duplicates: list[UserAchievementModel] = []
        for user_achievement in result.scalars().all():
            if user_achievement.achievement_id in seen_achievement_ids:
                duplicates.append(user_achievement)
                continue
            seen_achievement_ids.add(user_achievement.achievement_id)

        if not duplicates:
            return

        for duplicate in duplicates:
            await self.session.delete(duplicate)
        await self.session.commit()

    def _add_user_achievement(
        self,
        user_id: int,
        achievement_id: int,
        awarded_at: datetime,
    ) -> None:
        self.session.add(
            UserAchievementModel(
                user_id=user_id,
                achievement_id=achievement_id,
                awarded_at=awarded_at,
            )
        )

    async def _ensure_default_achievements(self) -> None:
        changed = False
        for payload in load_default_achievements():
            statement = select(AchievementModel).where(AchievementModel.criteria == payload["criteria"])
            if payload["points_required"] is None:
                statement = statement.where(AchievementModel.points_required.is_(None))
            else:
                statement = statement.where(AchievementModel.points_required == payload["points_required"])

            result = await self.session.execute(statement.order_by(AchievementModel.id.asc()))
            achievements = result.scalars().all()
            if not achievements:
                self.session.add(AchievementModel(image_file_id=None, **payload))
                changed = True
                continue

            achievement = achievements[0]
            for duplicate in achievements[1:]:
                await self._move_user_achievements_to_canonical(
                    canonical_achievement_id=achievement.id,
                    duplicate_achievement_id=duplicate.id,
                )
                await self.session.delete(duplicate)
                changed = True

            if achievement.title != payload["title"] or achievement.description != payload["description"]:
                achievement.title = payload["title"]
                achievement.description = payload["description"]
                changed = True
        if changed:
            await self.session.commit()

    async def _move_user_achievements_to_canonical(
        self,
        canonical_achievement_id: int,
        duplicate_achievement_id: int,
    ) -> None:
        duplicate_result = await self.session.execute(
            select(UserAchievementModel)
            .where(UserAchievementModel.achievement_id == duplicate_achievement_id)
            .order_by(UserAchievementModel.awarded_at.asc(), UserAchievementModel.id.asc())
        )
        for duplicate_user_achievement in duplicate_result.scalars().all():
            canonical_result = await self.session.execute(
                select(UserAchievementModel)
                .where(
                    UserAchievementModel.user_id == duplicate_user_achievement.user_id,
                    UserAchievementModel.achievement_id == canonical_achievement_id,
                )
                .order_by(UserAchievementModel.awarded_at.asc(), UserAchievementModel.id.asc())
            )
            canonical_user_achievement = canonical_result.scalars().first()
            if canonical_user_achievement is None:
                duplicate_user_achievement.achievement_id = canonical_achievement_id
                continue

            if duplicate_user_achievement.awarded_at < canonical_user_achievement.awarded_at:
                canonical_user_achievement.awarded_at = duplicate_user_achievement.awarded_at
            await self.session.delete(duplicate_user_achievement)

    async def _get_achievement(self, achievement_id: int) -> AchievementModel:
        await self._ensure_default_achievements()
        result = await self.session.execute(select(AchievementModel).where(AchievementModel.id == achievement_id))
        achievement = result.scalar_one_or_none()
        if achievement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Achievement not found",
            )
        return achievement

    async def _get_user(self, user_id: int) -> UserModel:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def _get_user_rating_place(self, user: UserModel) -> int | None:
        if user.role != UserRole.USER:
            return None
        place_expr = func.row_number().over(order_by=(UserModel.total_points.desc(), UserModel.id.asc()))
        ranked_users = (
            select(
                UserModel.id.label("id"),
                place_expr.label("place"),
            )
            .where(UserModel.role == UserRole.USER)
            .subquery()
        )
        result = await self.session.execute(select(ranked_users.c.place).where(ranked_users.c.id == user.id))
        return result.scalar_one_or_none()

    async def _get_user_team_rating_place(self, user: UserModel) -> int | None:
        if user.team_id is None:
            return None
        team_points = (
            select(
                TeamModel.id.label("id"),
                func.coalesce(func.sum(UserModel.total_points), 0).label("points"),
            )
            .select_from(TeamModel)
            .outerjoin(UserModel, UserModel.team_id == TeamModel.id)
            .group_by(TeamModel.id)
            .subquery()
        )
        place_expr = func.row_number().over(order_by=(team_points.c.points.desc(), team_points.c.id.asc()))
        ranked_teams = (
            select(
                team_points.c.id,
                place_expr.label("place"),
            )
            .subquery()
        )
        result = await self.session.execute(select(ranked_teams.c.place).where(ranked_teams.c.id == user.team_id))
        return result.scalar_one_or_none()

    @staticmethod
    def _matches_achievement(
        user: UserModel,
        achievement: AchievementModel,
        user_place: int | None,
        team_place: int | None,
    ) -> bool:
        if achievement.criteria == AchievementCriteria.POINTS:
            return achievement.points_required is not None and user.total_points >= achievement.points_required
        if achievement.criteria == AchievementCriteria.RATING_FIRST_PLACE:
            return user_place == 1
        if achievement.criteria == AchievementCriteria.TEAM_RATING_FIRST_PLACE:
            return team_place == 1
        return False
