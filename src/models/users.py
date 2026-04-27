import datetime
from enum import Enum

from sqlalchemy import ForeignKey, String
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
