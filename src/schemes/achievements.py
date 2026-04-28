from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, ConfigDict


class AchievementFilters(BaseModel):
    limit: int = 10
    offset: int = 0

    @classmethod
    def as_query(
        cls,
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> "AchievementFilters":
        return cls(limit=limit, offset=offset)


class AchievementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    image_file_id: str | None


class UserAchievementResponse(AchievementResponse):
    awarded_at: datetime


class AchievementPageResponse(BaseModel):
    items: list[AchievementResponse]
    total: int
    limit: int
    offset: int


class UserAchievementPageResponse(BaseModel):
    items: list[UserAchievementResponse]
    total: int
    limit: int
    offset: int
