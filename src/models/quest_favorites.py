from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class QuestFavoriteModel(Base):
    __tablename__ = "quest_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "quest_id", name="uq_quest_favorites_user_quest"),
    )

    id: Mapped[intpk]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"), nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="favorite_quests")
    quest: Mapped["QuestModel"] = relationship("QuestModel", back_populates="favorites")
