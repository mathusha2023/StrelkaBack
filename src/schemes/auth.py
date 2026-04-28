from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserRoleSchema(str, Enum):
    USER = "user"
    MODERATOR = "moderator"


class UserCreate(BaseModel):
    email: str
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    birthdate: date


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=255)
    birthdate: date | None = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> "UserUpdate":
        if self.username is None and self.birthdate is None:
            raise ValueError("At least one field must be provided")
        return self


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=255)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    birthdate: date
    role: UserRoleSchema
    team_name: str | None = None
    total_points: int = 0


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
