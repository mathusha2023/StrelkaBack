import json
from enum import Enum

from fastapi import Form, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

QUEST_POINTS_FORM_EXAMPLE = (
    '[{"title":"Старый мост","latitude":55.751244,"longitude":37.618423,'
    '"task":"Найдите табличку на опоре моста и укажите номер, указанный на ней.",'
    '"correct_answer":"42","hint":"Табличка со стороны реки",'
    '"point_rules":"Не выходить на проезжую часть"}]'
)


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
    points: list["QuestPointCreate"] = Field(
        min_length=1,
        json_schema_extra={
            "example": [
                {
                    "title": "Старый мост",
                    "latitude": 55.751244,
                    "longitude": 37.618423,
                    "task": "Найдите табличку на опоре моста и укажите номер, указанный на ней.",
                    "correct_answer": "42",
                    "hint": "Табличка со стороны реки",
                    "point_rules": "Не выходить на проезжую часть",
                }
            ]
        },
    )

    @classmethod
    def as_form(
        cls,
        title: str = Form(min_length=5, max_length=255),
        description: str = Form(min_length=30, max_length=5000),
        location: str = Form(min_length=1, max_length=255),
        difficulty: int = Form(ge=1, le=5),
        duration_minutes: int = Form(gt=0),
        rules_and_warnings: str | None = Form(default=None, max_length=5000),
        points: str = Form(
            default=QUEST_POINTS_FORM_EXAMPLE,
            description="JSON-массив точек квеста",
            openapi_examples={
                "quest_points": {
                    "summary": "Пример массива точек",
                    "value": QUEST_POINTS_FORM_EXAMPLE,
                }
            },
        ),
    ) -> "QuestCreate":
        try:
            raw_points = json.loads(points)
            parsed_points = TypeAdapter(list[QuestPointCreate]).validate_python(raw_points)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid points payload: {exc}",
            ) from exc

        return cls(
            title=title,
            description=description,
            location=location,
            difficulty=difficulty,
            duration_minutes=duration_minutes,
            rules_and_warnings=rules_and_warnings,
            points=parsed_points,
        )


class QuestPointCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    task: str = Field(min_length=20, max_length=5000)
    correct_answer: str = Field(min_length=1, max_length=500)
    hint: str | None = Field(default=None, max_length=1000)
    point_rules: str | None = Field(default=None, max_length=1000)


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


class QuestPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    latitude: float
    longitude: float
    task: str
    correct_answer: str
    hint: str | None
    point_rules: str | None


class QuestDetailResponse(QuestResponse):
    points: list[QuestPointResponse]


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
