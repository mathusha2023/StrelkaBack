from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class QuestRunStatusSchema(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class CheckpointPassedView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    latitude: float
    longitude: float


class CheckpointCurrentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    latitude: float
    longitude: float
    task: str
    hint: str | None
    point_rules: str | None


class QuestRunProgressResponse(BaseModel):
    run_id: int
    quest_id: int
    status: QuestRunStatusSchema
    started_at: datetime
    completed_at: datetime | None
    total_checkpoints: int
    current_step_index: int
    previous_checkpoints: list[CheckpointPassedView]
    current_checkpoint: CheckpointCurrentView | None
    points_awarded: int | None


class QuestRunHistoryItem(BaseModel):
    run_id: int
    quest_id: int
    quest_title: str
    status: QuestRunStatusSchema
    started_at: datetime
    completed_at: datetime
    points_awarded: int


class QuestRunStartRequest(BaseModel):
    quest_id: int = Field(gt=0)


class QuestRunAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


class QuestRunAnswerResponse(BaseModel):
    correct: bool
    progress: QuestRunProgressResponse
    points_earned: int | None = None
