from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class QuestComplaintModel(Base):
    __tablename__ = "quest_complaints"

    id: Mapped[intpk]
    reason: Mapped[str] = mapped_column(Text)
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    quest: Mapped["QuestModel"] = relationship("QuestModel", back_populates="complaints")
    author: Mapped["UserModel"] = relationship("UserModel", back_populates="created_quest_complaints")
