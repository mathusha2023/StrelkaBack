import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base
from src.database.data_types import intpk


class TeamQuestRunStatus(str, Enum):
    WAITING_FOR_TEAM = "waiting_for_team"
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TeamQuestRunModel(Base):
    __tablename__ = "team_quest_runs"
    __table_args__ = (
        Index(
            "uq_team_quest_runs_one_active_per_team",
            "team_id",
            unique=True,
            postgresql_where=text("status IN ('waiting_for_team', 'starting', 'in_progress')"),
        ),
    )

    id: Mapped[intpk]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[TeamQuestRunStatus] = mapped_column(
        SAEnum(TeamQuestRunStatus, native_enum=False, values_callable=lambda m: [e.value for e in m]),
        default=TeamQuestRunStatus.WAITING_FOR_TEAM,
        nullable=False,
    )
    starts_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)

    team: Mapped["TeamModel"] = relationship("TeamModel", back_populates="team_quest_runs")
    quest: Mapped["QuestModel"] = relationship("QuestModel", back_populates="team_runs")
    participants: Mapped[list["TeamQuestRunParticipantModel"]] = relationship(
        "TeamQuestRunParticipantModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    checkpoints: Mapped[list["TeamQuestRunCheckpointModel"]] = relationship(
        "TeamQuestRunCheckpointModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class TeamQuestRunParticipantModel(Base):
    __tablename__ = "team_quest_run_participants"
    __table_args__ = (
        UniqueConstraint("run_id", "user_id", name="uq_team_quest_run_participants_run_user"),
    )

    id: Mapped[intpk]
    run_id: Mapped[int] = mapped_column(ForeignKey("team_quest_runs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ready_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    run: Mapped["TeamQuestRunModel"] = relationship("TeamQuestRunModel", back_populates="participants")
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="team_quest_run_participants")


class TeamQuestRunCheckpointModel(Base):
    __tablename__ = "team_quest_run_checkpoints"
    __table_args__ = (
        UniqueConstraint("run_id", "quest_point_id", name="uq_team_quest_run_checkpoints_run_point"),
    )

    id: Mapped[intpk]
    run_id: Mapped[int] = mapped_column(ForeignKey("team_quest_runs.id", ondelete="CASCADE"), nullable=False)
    quest_point_id: Mapped[int] = mapped_column(ForeignKey("quest_points.id", ondelete="CASCADE"), nullable=False)
    completed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    completed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))

    run: Mapped["TeamQuestRunModel"] = relationship("TeamQuestRunModel", back_populates="checkpoints")
    quest_point: Mapped["QuestPointModel"] = relationship("QuestPointModel")
    completed_by_user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="completed_team_quest_checkpoints",
    )
