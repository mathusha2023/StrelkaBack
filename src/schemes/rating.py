from fastapi import Query
from pydantic import BaseModel, Field


class RatingFilters(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @classmethod
    def as_query(
        cls,
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> "RatingFilters":
        return cls(limit=limit, offset=offset)


class RatingEntry(BaseModel):
    name: str
    points: int
    place: int


class UserRatingPageResponse(BaseModel):
    items: list[RatingEntry]
    total: int
    limit: int
    offset: int
    current_user: RatingEntry


class TeamRatingPageResponse(BaseModel):
    items: list[RatingEntry]
    total: int
    limit: int
    offset: int
    current_user_team: RatingEntry | None
