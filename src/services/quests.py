import re
from difflib import SequenceMatcher

from fastapi import HTTPException, status
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.quests import QuestModel, QuestStatus
from src.models.quest_complaints import QuestComplaintModel
from src.models.users import UserModel
from src.schemes.auth import UserResponse
from src.schemes.quests import (
    QuestArchiveStatusSchema,
    QuestComplaintCreateRequest,
    QuestComplaintPageResponse,
    QuestComplaintResponse,
    QuestCreate,
    QuestListFilters,
    QuestPageResponse,
    QuestResponse,
)
from src.services.minio import MinioService


class QuestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_quest(
        self,
        current_user: UserResponse,
        payload: QuestCreate,
        image: UploadFile | None = None,
    ) -> QuestResponse:
        image_file_id = None
        if image is not None:
            image_file_id = await MinioService.upload_file_with_uuid(
                data=image.file,
                content_type=image.content_type or "application/octet-stream",
                original_filename=image.filename,
            )

        quest = QuestModel(
            title=payload.title,
            description=payload.description,
            location=payload.location,
            difficulty=payload.difficulty,
            duration_minutes=payload.duration_minutes,
            rules_and_warnings=payload.rules_and_warnings,
            image_file_id=image_file_id,
            rejection_reason=None,
            status=QuestStatus.ON_MODERATION,
            creator_id=current_user.id,
        )
        self.session.add(quest)
        await self.session.commit()
        await self.session.refresh(quest)

        return await self._get_quest_response(quest.id)

    async def get_quest(self, quest_id: int) -> QuestResponse:
        quest = await self._get_quest(quest_id)
        if quest.status != QuestStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest not found",
            )
        return QuestResponse.model_validate(quest)

    async def get_my_quests(
        self,
        current_user: UserResponse,
        filters: QuestListFilters,
    ) -> QuestPageResponse:
        return await self._get_paginated_quests(
            select(QuestModel)
            .options(selectinload(QuestModel.creator).selectinload(UserModel.team))
            .where(QuestModel.creator_id == current_user.id)
            .order_by(QuestModel.id.desc()),
            filters,
        )

    async def get_all_quests(self, filters: QuestListFilters) -> QuestPageResponse:
        return await self._get_paginated_quests(
            select(QuestModel)
            .options(selectinload(QuestModel.creator).selectinload(UserModel.team))
            .where(QuestModel.status == QuestStatus.PUBLISHED)
            .order_by(QuestModel.id.desc()),
            filters,
        )

    async def get_quests_on_moderation(self, filters: QuestListFilters) -> QuestPageResponse:
        return await self._get_paginated_quests(
            select(QuestModel)
            .options(selectinload(QuestModel.creator).selectinload(UserModel.team))
            .where(QuestModel.status == QuestStatus.ON_MODERATION)
            .order_by(QuestModel.id.desc()),
            filters,
        )

    async def publish_quest(self, quest_id: int) -> QuestResponse:
        return await self._update_quest_status(
            quest_id=quest_id,
            expected_status=QuestStatus.ON_MODERATION,
            new_status=QuestStatus.PUBLISHED,
        )

    async def reject_quest(self, quest_id: int, reason: str) -> QuestResponse:
        return await self._update_quest_status(
            quest_id=quest_id,
            expected_status=QuestStatus.ON_MODERATION,
            new_status=QuestStatus.REJECTED,
            rejection_reason=reason,
        )

    async def update_my_quest_archive_status(
        self,
        current_user: UserResponse,
        quest_id: int,
        target_status: QuestArchiveStatusSchema,
    ) -> QuestResponse:
        quest = await self._get_quest(quest_id)
        self._ensure_creator(current_user, quest)

        current_status = quest.status
        target_quest_status = QuestStatus(target_status.value)
        allowed_transitions = {
            (QuestStatus.PUBLISHED, QuestStatus.ARCHIVED),
            (QuestStatus.ARCHIVED, QuestStatus.PUBLISHED),
        }
        if (current_status, target_quest_status) not in allowed_transitions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Only transitions published -> archived and archived -> published are allowed"
                ),
            )

        quest.status = target_quest_status
        if target_quest_status == QuestStatus.PUBLISHED:
            quest.rejection_reason = None
        await self.session.commit()
        await self.session.refresh(quest)
        return QuestResponse.model_validate(quest)

    async def delete_my_quest(self, current_user: UserResponse, quest_id: int) -> None:
        quest = await self._get_quest(quest_id)
        self._ensure_creator(current_user, quest)
        await self.session.delete(quest)
        await self.session.commit()

    async def delete_quest_as_moderator(self, quest_id: int) -> None:
        quest = await self._get_quest(quest_id)
        await self.session.delete(quest)
        await self.session.commit()

    async def create_complaint(
        self,
        current_user: UserResponse,
        quest_id: int,
        payload: QuestComplaintCreateRequest,
    ) -> QuestComplaintResponse:
        quest = await self._get_quest(quest_id)
        if quest.status != QuestStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Complaint can be created only for published quests",
            )
        complaint = QuestComplaintModel(
            reason=payload.reason,
            quest_id=quest.id,
            author_id=current_user.id,
        )
        self.session.add(complaint)
        await self.session.commit()
        await self.session.refresh(complaint)
        loaded_complaint = await self._get_complaint(complaint.id)
        return QuestComplaintResponse.model_validate(loaded_complaint)

    async def get_all_complaints(self, limit: int = 20, offset: int = 0) -> QuestComplaintPageResponse:
        statement = (
            select(QuestComplaintModel)
            .options(selectinload(QuestComplaintModel.author))
            .order_by(QuestComplaintModel.id.desc())
        )
        result = await self.session.execute(statement)
        complaints = result.scalars().all()
        total = len(complaints)
        items = [
            QuestComplaintResponse.model_validate(complaint)
            for complaint in complaints[offset : offset + limit]
        ]
        return QuestComplaintPageResponse(items=items, total=total, limit=limit, offset=offset)

    async def delete_complaint(self, complaint_id: int) -> None:
        complaint = await self._get_complaint(complaint_id)
        await self.session.delete(complaint)
        await self.session.commit()

    async def _get_paginated_quests(self, statement, filters: QuestListFilters) -> QuestPageResponse:
        statement = self._apply_sql_filters(statement, filters)
        result = await self.session.execute(statement)
        quests = result.scalars().all()

        if filters.city:
            quests = [
                quest for quest in quests
                if self._matches_city_filter(quest.location, filters.city)
            ]

        total = len(quests)
        start = filters.offset
        end = filters.offset + filters.limit
        items = [QuestResponse.model_validate(quest) for quest in quests[start:end]]
        return QuestPageResponse(
            items=items,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    async def _get_quest(self, quest_id: int) -> QuestModel:
        result = await self.session.execute(
            select(QuestModel)
            .options(selectinload(QuestModel.creator).selectinload(UserModel.team))
            .where(QuestModel.id == quest_id)
        )
        quest = result.scalar_one_or_none()
        if quest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest not found",
            )
        return quest

    async def _get_quest_response(self, quest_id: int) -> QuestResponse:
        quest = await self._get_quest(quest_id)
        return QuestResponse.model_validate(quest)

    async def _get_complaint(self, complaint_id: int) -> QuestComplaintModel:
        result = await self.session.execute(
            select(QuestComplaintModel)
            .options(selectinload(QuestComplaintModel.author))
            .where(QuestComplaintModel.id == complaint_id)
        )
        complaint = result.scalar_one_or_none()
        if complaint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Complaint not found",
            )
        return complaint

    async def _update_quest_status(
        self,
        quest_id: int,
        expected_status: QuestStatus,
        new_status: QuestStatus,
        rejection_reason: str | None = None,
    ) -> QuestResponse:
        quest = await self._get_quest(quest_id)
        if quest.status != expected_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Quest status transition is not allowed: "
                    f"{quest.status.value} -> {new_status.value}"
                ),
            )

        quest.status = new_status
        quest.rejection_reason = rejection_reason
        await self.session.commit()
        await self.session.refresh(quest)
        return QuestResponse.model_validate(quest)

    @staticmethod
    def _ensure_creator(current_user: UserResponse, quest: QuestModel) -> None:
        if current_user.id != quest.creator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this quest",
            )

    @staticmethod
    def _apply_sql_filters(statement, filters: QuestListFilters):
        if filters.min_duration_minutes is not None:
            statement = statement.where(QuestModel.duration_minutes >= filters.min_duration_minutes)
        if filters.max_duration_minutes is not None:
            statement = statement.where(QuestModel.duration_minutes <= filters.max_duration_minutes)
        if filters.difficulties:
            statement = statement.where(QuestModel.difficulty.in_(filters.difficulties))
        return statement

    @classmethod
    def _matches_city_filter(cls, location: str, city: str) -> bool:
        normalized_location = cls._normalize_text(location)
        normalized_city = cls._normalize_text(city)
        if not normalized_city:
            return True

        if normalized_city in normalized_location:
            return True

        location_parts = [part for part in re.split(r"\s+", normalized_location) if part]
        city_parts = [part for part in re.split(r"\s+", normalized_city) if part]

        candidates = [normalized_location, *location_parts]
        if city_parts:
            candidates.extend(city_parts)

        best_ratio = max(
            SequenceMatcher(None, normalized_city, candidate).ratio()
            for candidate in candidates
            if candidate
        )
        return best_ratio >= 0.72

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = value.lower().replace("ё", "е")
        value = re.sub(r"[^a-zа-я0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value
