from enum import Enum

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk

class QuestStatus(str, Enum):
    ON_MODERATION = "on_moderation"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class QuestModel(Base):
    __tablename__ = "quests"

    id: Mapped[intpk]
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(255))
    difficulty: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    rules_and_warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[QuestStatus] = mapped_column(default=QuestStatus.ON_MODERATION)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    creator: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="created_quests",
        foreign_keys=[creator_id],
    )
    complaints: Mapped[list["QuestComplaintModel"]] = relationship(
        "QuestComplaintModel",
        back_populates="quest",
        cascade="all, delete-orphan",
    )
    points: Mapped[list["QuestPointModel"]] = relationship(
        "QuestPointModel",
        back_populates="quest",
        cascade="all, delete-orphan",
        order_by="QuestPointModel.id",
    )
    favorites: Mapped[list["QuestFavoriteModel"]] = relationship(
        "QuestFavoriteModel",
        back_populates="quest",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["QuestRunModel"]] = relationship(
        "QuestRunModel",
        back_populates="quest",
        cascade="all, delete-orphan",
    )
    team_runs: Mapped[list["TeamQuestRunModel"]] = relationship(
        "TeamQuestRunModel",
        back_populates="quest",
        cascade="all, delete-orphan",
    )
