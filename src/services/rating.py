from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.teams import TeamModel
from src.models.users import UserModel, UserRole
from src.schemes.auth import UserResponse
from src.schemes.rating import (
    RatingEntry,
    RatingFilters,
    TeamRatingPageResponse,
    UserRatingPageResponse,
)


class RatingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_users_rating(
        self,
        current_user: UserResponse,
        filters: RatingFilters,
    ) -> UserRatingPageResponse:
        ranked_users = self._users_ranked_subquery()
        items_result = await self.session.execute(
            select(
                ranked_users.c.name,
                ranked_users.c.points,
                ranked_users.c.place,
            )
            .order_by(ranked_users.c.place)
            .offset(filters.offset)
            .limit(filters.limit)
        )
        items = [
            RatingEntry(name=row.name, points=row.points, place=row.place)
            for row in items_result.all()
        ]

        total_result = await self.session.execute(select(func.count()).select_from(ranked_users))
        total = int(total_result.scalar_one())

        current_result = await self.session.execute(
            select(
                ranked_users.c.name,
                ranked_users.c.points,
                ranked_users.c.place,
            ).where(ranked_users.c.id == current_user.id)
        )
        current_row = current_result.one_or_none()
        if current_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Current user not found in rating",
            )
        current_entry = RatingEntry(
            name=current_row.name,
            points=current_row.points,
            place=current_row.place,
        )
        return UserRatingPageResponse(
            items=items,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
            current_user=current_entry,
        )

    async def get_teams_rating(
        self,
        current_user: UserResponse,
        filters: RatingFilters,
    ) -> TeamRatingPageResponse:
        ranked_teams = self._teams_ranked_subquery()
        items_result = await self.session.execute(
            select(
                ranked_teams.c.name,
                ranked_teams.c.points,
                ranked_teams.c.place,
            )
            .order_by(ranked_teams.c.place)
            .offset(filters.offset)
            .limit(filters.limit)
        )
        items = [
            RatingEntry(name=row.name, points=row.points, place=row.place)
            for row in items_result.all()
        ]

        total_result = await self.session.execute(select(func.count()).select_from(ranked_teams))
        total = int(total_result.scalar_one())

        current_team_result = await self.session.execute(
            select(UserModel.team_id).where(UserModel.id == current_user.id)
        )
        current_team_id = current_team_result.scalar_one_or_none()
        current_team_entry: RatingEntry | None = None
        if current_team_id is not None:
            current_team_rank_result = await self.session.execute(
                select(
                    ranked_teams.c.name,
                    ranked_teams.c.points,
                    ranked_teams.c.place,
                ).where(ranked_teams.c.id == current_team_id)
            )
            current_team_row = current_team_rank_result.one_or_none()
            if current_team_row is not None:
                current_team_entry = RatingEntry(
                    name=current_team_row.name,
                    points=current_team_row.points,
                    place=current_team_row.place,
                )
        return TeamRatingPageResponse(
            items=items,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
            current_user_team=current_team_entry,
        )

    @staticmethod
    def _users_ranked_subquery():
        place_expr = func.row_number().over(
            order_by=(UserModel.total_points.desc(), UserModel.id.asc())
        )
        return (
            select(
                UserModel.id.label("id"),
                UserModel.username.label("name"),
                UserModel.total_points.label("points"),
                place_expr.label("place"),
            )
            .select_from(UserModel)
            .where(UserModel.role == UserRole.USER)
            .subquery()
        )

    @staticmethod
    def _teams_ranked_subquery():
        team_points = (
            select(
                TeamModel.id.label("id"),
                TeamModel.name.label("name"),
                func.coalesce(func.sum(UserModel.total_points), 0).label("points"),
            )
            .select_from(TeamModel)
            .outerjoin(UserModel, UserModel.team_id == TeamModel.id)
            .group_by(TeamModel.id, TeamModel.name)
            .subquery()
        )
        place_expr = func.row_number().over(
            order_by=(team_points.c.points.desc(), team_points.c.id.asc())
        )
        return (
            select(
                team_points.c.id,
                team_points.c.name,
                team_points.c.points,
                place_expr.label("place"),
            )
            .subquery()
        )
