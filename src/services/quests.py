import re
from difflib import SequenceMatcher

from fastapi import HTTPException, status
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.quests import QuestModel, QuestStatus
from src.models.users import UserModel
from src.schemes.auth import UserResponse
from src.schemes.quests import QuestCreate, QuestListFilters, QuestPageResponse, QuestResponse
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
            status=QuestStatus.DRAFT,
            creator_id=current_user.id,
        )
        self.session.add(quest)
        await self.session.commit()
        await self.session.refresh(quest)

        return await self.get_quest(quest.id)

    async def get_quest(self, quest_id: int) -> QuestResponse:
        quest = await self._get_quest(quest_id)
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
            .order_by(QuestModel.id.desc()),
            filters,
        )

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
