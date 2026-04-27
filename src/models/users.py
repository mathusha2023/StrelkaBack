import datetime
from enum import Enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

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
