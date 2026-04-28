from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TeamQuestRunStatusSchema(str, Enum):
    WAITING_FOR_TEAM = "waiting_for_team"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TeamQuestRunReadinessRequest(BaseModel):
    quest_id: int = Field(gt=0)
    is_ready: bool


class TeamQuestRunCheckpointAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


class TeamQuestRunCheckpointView(BaseModel):
    id: int
    title: str
    latitude: float
    longitude: float
    task: str
    hint: str | None
    point_rules: str | None
    is_completed: bool
    completed_by_user_id: int | None
    completed_at: datetime | None


class TeamQuestRunProgressResponse(BaseModel):
    run_id: int
    team_id: int
    quest_id: int
    status: TeamQuestRunStatusSchema
    ready_member_ids: list[int]
    total_members: int
    starts_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    total_checkpoints: int
    completed_checkpoints: int
    checkpoints: list[TeamQuestRunCheckpointView]
    points_awarded: int | None


class TeamQuestRunCheckpointAnswerResponse(BaseModel):
    correct: bool
    progress: TeamQuestRunProgressResponse
    points_earned: int | None = None
