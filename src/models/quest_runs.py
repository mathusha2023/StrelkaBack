"""Quest runs: a separate `quest_runs` table.

Each row is a single run (active or finished). A user can have at most one row
with status `in_progress` (see the partial unique index).
"""

import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class QuestRunStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class QuestRunModel(Base):
    """One row per quest run (history + the current active run)."""

    __tablename__ = "quest_runs"
    __table_args__ = (
        Index(
            "uq_quest_runs_one_in_progress_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[QuestRunStatus] = mapped_column(
        SAEnum(QuestRunStatus, native_enum=False, values_callable=lambda m: [e.value for e in m]),
        default=QuestRunStatus.IN_PROGRESS,
        nullable=False,
    )
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step_index: Mapped[int] = mapped_column(Integer, default=0)
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="quest_runs")
    quest: Mapped["QuestModel"] = relationship("QuestModel", back_populates="runs")
