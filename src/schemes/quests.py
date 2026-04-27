from enum import Enum

from fastapi import Form, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class QuestStatusSchema(str, Enum):
    ON_MODERATION = "on_moderation"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class QuestCreate(BaseModel):
    title: str = Field(min_length=5, max_length=255)
    description: str = Field(min_length=30, max_length=5000)
    location: str = Field(min_length=1, max_length=255)
    difficulty: int = Field(ge=1, le=5)
    duration_minutes: int = Field(gt=0)
    rules_and_warnings: str | None = Field(default=None, max_length=5000)

    @classmethod
    def as_form(
        cls,
        title: str = Form(min_length=5, max_length=255),
        description: str = Form(min_length=30, max_length=5000),
        location: str = Form(min_length=1, max_length=255),
        difficulty: int = Form(ge=1, le=5),
        duration_minutes: int = Form(gt=0),
        rules_and_warnings: str | None = Form(default=None, max_length=5000),
    ) -> "QuestCreate":
        return cls(
            title=title,
            description=description,
            location=location,
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            rules_and_warnings=rules_and_warnings,
        )


class QuestCreatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    team_name: str | None = None


class QuestListFilters(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    min_duration_minutes: int | None = Field(default=None, ge=1)
    max_duration_minutes: int | None = Field(default=None, ge=1)
    difficulties: list[int] | None = None
    city: str | None = Field(default=None, min_length=1, max_length=255)

    @classmethod
    def as_query(
        cls,
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        min_duration_minutes: int | None = Query(default=None, ge=1),
        max_duration_minutes: int | None = Query(default=None, ge=1),
        difficulties: list[int] | None = Query(default=None),
        city: str | None = Query(default=None, min_length=1, max_length=255),
    ) -> "QuestListFilters":
        if difficulties is not None:
            invalid_difficulties = [difficulty for difficulty in difficulties if not 1 <= difficulty <= 5]
            if invalid_difficulties:
                raise HTTPException(
                    status_code=400,
                    detail="Difficulty values must be between 1 and 5",
                )
        if (
            min_duration_minutes is not None
            and max_duration_minutes is not None
            and min_duration_minutes > max_duration_minutes
        ):
            raise HTTPException(
                status_code=400,
                detail="min_duration_minutes cannot be greater than max_duration_minutes",
            )
        return cls(
            limit=limit,
            offset=offset,
            min_duration_minutes=min_duration_minutes,
            max_duration_minutes=max_duration_minutes,
            difficulties=difficulties,
            city=city,
        )


class QuestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    location: str
    difficulty: int
    duration_minutes: int
    rules_and_warnings: str | None
    image_file_id: str | None
    rejection_reason: str | None
    status: QuestStatusSchema
    creator: QuestCreatorResponse


class QuestRejectRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class QuestArchiveStatusSchema(str, Enum):
    PUBLISHED = "published"
    ARCHIVED = "archived"


class QuestArchiveStatusUpdateRequest(BaseModel):
    status: QuestArchiveStatusSchema


class QuestComplaintCreateRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class QuestComplaintAuthorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class QuestComplaintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reason: str
    quest_id: int
    author: QuestComplaintAuthorResponse


class QuestComplaintPageResponse(BaseModel):
    items: list[QuestComplaintResponse]
    total: int
    limit: int
    offset: int


class QuestPageResponse(BaseModel):
    items: list[QuestResponse]
    total: int
    limit: int
    offset: int
