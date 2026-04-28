from pydantic import BaseModel, ConfigDict, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)


class TeamJoinRequest(BaseModel):
    code: str = Field(min_length=12, max_length=12)


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    age: int


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    code: str
    creator_id: int
    members_count: int
    total_points: int
    members: list[TeamMemberResponse]
