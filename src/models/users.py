from sqlalchemy.orm import Mapped
from src.database.base import Base
from src.database.data_types import intpk


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[intpk]
    username: Mapped[str]
