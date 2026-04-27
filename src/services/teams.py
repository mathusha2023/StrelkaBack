import secrets
import string

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.teams import TeamModel
from src.models.users import UserModel
from src.schemes.auth import UserResponse
from src.schemes.teams import TeamCreate, TeamResponse

TEAM_CODE_ALPHABET = string.ascii_uppercase + string.digits
TEAM_CODE_LENGTH = 12
TEAM_MAX_MEMBERS = 6


class TeamService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_team(self, current_user: UserResponse, payload: TeamCreate) -> TeamResponse:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already in a team",
            )

        team = TeamModel(
            name=payload.name,
            description=payload.description,
            code=await self._generate_unique_team_code(),
            creator_id=db_user.id,
        )
        self.session.add(team)
        await self.session.flush()

        db_user.team_id = team.id
        await self.session.commit()

        return await self._get_team_response(team.id)

    async def get_my_team(self, current_user: UserResponse) -> TeamResponse:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User is not in a team",
            )

        return await self._get_team_response(db_user.team_id)

    async def join_team(self, current_user: UserResponse, code: str) -> TeamResponse:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already in a team",
            )

        team = await self._get_team_by_code(code.upper())
        members_count = await self._get_team_members_count(team.id)
        if members_count >= TEAM_MAX_MEMBERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team is full",
            )

        db_user.team_id = team.id
        await self.session.commit()

        return await self._get_team_response(team.id)

    async def leave_team(self, current_user: UserResponse) -> None:
        db_user = await self._get_user(current_user.id)
        if db_user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not in a team",
            )
        if await self._is_team_creator(db_user.id, db_user.team_id):
            members_count = await self._get_team_members_count(db_user.team_id)
            if members_count == 1:
                team = await self._get_team(db_user.team_id)
                db_user.team_id = None
                await self.session.delete(team)
                await self.session.commit()
                return
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Team creator cannot leave the team",
            )

        db_user.team_id = None
        await self.session.commit()

    async def kick_member(self, current_user: UserResponse, member_id: int) -> TeamResponse:
        creator = await self._get_user(current_user.id)
        if creator.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Creator is not in a team",
            )

        team = await self._get_team(creator.team_id)
        if team.creator_id != creator.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only team creator can remove members",
            )
        if member_id == creator.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Creator cannot remove themselves from the team",
            )

        member = await self._get_user(member_id)
        if member.team_id != team.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a member of this team",
            )

        team_id = team.id
        member.team_id = None
        await self.session.commit()
        self.session.expire_all()

        return await self._get_team_response(team_id)

    async def _get_team(self, team_id: int) -> TeamModel:
        result = await self.session.execute(
            select(TeamModel)
            .options(selectinload(TeamModel.members))
            .where(TeamModel.id == team_id)
        )
        team = result.scalar_one_or_none()
        if team is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )
        return team

    async def _get_team_by_code(self, code: str) -> TeamModel:
        result = await self.session.execute(select(TeamModel).where(TeamModel.code == code))
        team = result.scalar_one_or_none()
        if team is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )
        return team

    async def _get_user(self, user_id: int) -> UserModel:
        result = await self.session.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user

    async def _get_team_members_count(self, team_id: int) -> int:
        result = await self.session.execute(
            select(func.count(UserModel.id)).where(UserModel.team_id == team_id)
        )
        return int(result.scalar_one())

    async def _is_team_creator(self, user_id: int, team_id: int) -> bool:
        result = await self.session.execute(
            select(TeamModel.id).where(TeamModel.id == team_id, TeamModel.creator_id == user_id)
        )
        return result.scalar_one_or_none() is not None

    async def _generate_unique_team_code(self) -> str:
        while True:
            code = "".join(secrets.choice(TEAM_CODE_ALPHABET) for _ in range(TEAM_CODE_LENGTH))
            result = await self.session.execute(select(TeamModel.id).where(TeamModel.code == code))
            if result.scalar_one_or_none() is None:
                return code

    async def _get_team_response(self, team_id: int) -> TeamResponse:
        team = await self._get_team(team_id)
        return TeamResponse.model_validate(team)
