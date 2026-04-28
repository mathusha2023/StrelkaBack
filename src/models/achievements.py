import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class AchievementCriteria(str, Enum):
    POINTS = "points"
    RATING_FIRST_PLACE = "rating_first_place"
    TEAM_RATING_FIRST_PLACE = "team_rating_first_place"
    QUEST_UNDER_MINUTE = "quest_under_minute"


class AchievementModel(Base):
    __tablename__ = "achievements"

    id: Mapped[intpk]
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    image_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    criteria: Mapped[AchievementCriteria] = mapped_column(
        SAEnum(AchievementCriteria, native_enum=False, values_callable=lambda m: [e.value for e in m]),
        nullable=False,
    )
    points_required: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user_achievements: Mapped[list["UserAchievementModel"]] = relationship(
        "UserAchievementModel",
        back_populates="achievement",
        cascade="all, delete-orphan",
    )


class UserAchievementModel(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="uq_user_achievements_user_achievement"),
    )

    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False)
    awarded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="achievements")
    achievement: Mapped["AchievementModel"] = relationship("AchievementModel", back_populates="user_achievements")
