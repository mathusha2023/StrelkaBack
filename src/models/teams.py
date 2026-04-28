from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base
from src.database.data_types import intpk
from src.models.users import UserModel


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[intpk]
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    creator: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="created_teams",
        foreign_keys=[creator_id],
    )
    members: Mapped[list["UserModel"]] = relationship(
        "UserModel",
        back_populates="team",
        foreign_keys="UserModel.team_id",
    )
    team_quest_runs: Mapped[list["TeamQuestRunModel"]] = relationship(
        "TeamQuestRunModel",
        back_populates="team",
        cascade="all, delete-orphan",
    )

    @property
    def members_count(self) -> int:
        return len(self.members)

    @property
    def total_points(self) -> int:
        return sum(m.total_points for m in self.members)
