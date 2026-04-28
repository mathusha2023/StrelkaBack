"""Запуски квестов: отдельная таблица `quest_runs`.

Каждая строка — одно прохождение (активное или завершённое). У пользователя
не более одной строки со статусом `in_progress` (см. частичный уникальный индекс).
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
    """Одна запись = один забег по квесту (история прохождений и текущий активный)."""

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
