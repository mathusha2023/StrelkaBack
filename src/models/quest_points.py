from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class QuestPointModel(Base):
    __tablename__ = "quest_points"

    id: Mapped[intpk]
    title: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    task: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(String(500))
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    point_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"), nullable=False)

    quest: Mapped["QuestModel"] = relationship("QuestModel", back_populates="points")
