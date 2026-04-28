import datetime
from enum import Enum

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class UserRole(str, Enum):
    USER = "user"
    MODERATOR = "moderator"


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[intpk]
    username: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    birthdate: Mapped[datetime.date]
    role: Mapped[UserRole] = mapped_column(default=UserRole.USER)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    team: Mapped["TeamModel | None"] = relationship(
        "TeamModel",
        back_populates="members",
        foreign_keys=[team_id],
    )
    created_teams: Mapped[list["TeamModel"]] = relationship(
        "TeamModel",
        back_populates="creator",
        foreign_keys="TeamModel.creator_id",
    )
    created_quests: Mapped[list["QuestModel"]] = relationship(
        "QuestModel",
        back_populates="creator",
        foreign_keys="QuestModel.creator_id",
    )
    created_quest_complaints: Mapped[list["QuestComplaintModel"]] = relationship(
        "QuestComplaintModel",
        back_populates="author",
        foreign_keys="QuestComplaintModel.author_id",
    )
    favorite_quests: Mapped[list["QuestFavoriteModel"]] = relationship(
        "QuestFavoriteModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    quest_runs: Mapped[list["QuestRunModel"]] = relationship(
        "QuestRunModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    team_quest_run_participants: Mapped[list["TeamQuestRunParticipantModel"]] = relationship(
        "TeamQuestRunParticipantModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    completed_team_quest_checkpoints: Mapped[list["TeamQuestRunCheckpointModel"]] = relationship(
        "TeamQuestRunCheckpointModel",
        back_populates="completed_by_user",
        cascade="all, delete-orphan",
    )
    achievements: Mapped[list["UserAchievementModel"]] = relationship(
        "UserAchievementModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def age(self) -> int:
        today = datetime.date.today()
        years = today.year - self.birthdate.year
        if (today.month, today.day) < (self.birthdate.month, self.birthdate.day):
            years -= 1
        return years

    @property
    def team_name(self) -> str | None:
        return self.team.name if self.team is not None else None
