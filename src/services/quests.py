import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher

from fastapi import HTTPException, status
from fastapi import UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.quests import QuestModel, QuestStatus
from src.models.quest_complaints import QuestComplaintModel
from src.models.quest_favorites import QuestFavoriteModel
from src.models.quest_points import QuestPointModel
from src.models.quest_runs import QuestRunModel, QuestRunStatus
from src.models.users import UserModel, UserRole
from src.schemes.auth import UserResponse
from src.schemes.quests import (
    QuestArchiveStatusSchema,
    QuestComplaintCreateRequest,
    QuestComplaintPageResponse,
    QuestComplaintResponse,
    QuestCreate,
    QuestDetailResponse,
    QuestListFilters,
    QuestPageResponse,
    QuestResponse,
)
from src.services.minio import MinioService
from src.services.quest_pdf_export import QuestPdfExportService

NEAR_RADIUS_METERS = 1000
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")


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
        quest.points = [
            QuestPointModel(
                title=point.title,
                latitude=point.latitude,
                longitude=point.longitude,
                task=point.task,
                correct_answer=point.correct_answer,
                hint=point.hint,
                point_rules=point.point_rules,
            )
            for point in payload.points
        ]
        self.session.add(quest)
        await self.session.commit()
        await self.session.refresh(quest)

        return await self._get_quest_response(quest.id)

    async def get_quest(
            self,
            quest_id: int,
            current_user: UserResponse | None = None,
    ) -> QuestDetailResponse:
        quest = await self._get_quest_with_points(quest_id)
        is_moderator = (
                current_user is not None
                and current_user.role.value == UserRole.MODERATOR.value
        )
        if quest.status != QuestStatus.PUBLISHED and not is_moderator and (
                current_user is None or current_user.id != quest.creator_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest not found",
            )
        is_favourite = False
        is_completed = False
        if current_user is not None:
            is_favourite = await self._is_favourite(current_user.id, quest.id)
            is_completed = await self._is_completed(current_user.id, quest.id)
        best_map = await self._best_completion_seconds_by_quest_ids([quest.id])
        try:
            return QuestDetailResponse.from_quest_model(
                quest,
                is_favourite=is_favourite,
                is_completed=is_completed,
                best_completion_seconds=best_map.get(quest.id),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    async def export_quest_to_pdf(self, current_user: UserResponse, quest_id: int) -> bytes:
        quest = await self._get_quest_with_points(quest_id)
        if quest.status != QuestStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only published quests can be exported",
            )

        pdf_content = await asyncio.to_thread(QuestPdfExportService.build_quest_pdf, quest)
        await self._mark_exported_quest_completed(current_user.id, quest)
        return pdf_content

    async def get_my_quests(
            self,
            current_user: UserResponse,
            filters: QuestListFilters,
    ) -> QuestPageResponse:
        return await self._get_paginated_quests(
            select(QuestModel)
            .options(
                selectinload(QuestModel.creator).selectinload(UserModel.team),
                selectinload(QuestModel.points),
            )
            .where(QuestModel.creator_id == current_user.id)
            .order_by(QuestModel.id.desc()),
            filters,
            current_user=current_user,
        )

    async def get_all_quests(
            self,
            filters: QuestListFilters,
            current_user: UserResponse | None = None,
    ) -> QuestPageResponse:
        statement = (
            select(QuestModel)
            .options(
                selectinload(QuestModel.creator).selectinload(UserModel.team),
                selectinload(QuestModel.points),
            )
            .order_by(QuestModel.id.desc())
        )
        is_moderator = (
                current_user is not None
                and current_user.role.value == UserRole.MODERATOR.value
        )
        if not is_moderator:
            statement = statement.where(QuestModel.status == QuestStatus.PUBLISHED)

        statement = self._apply_near_radius_filter(statement, filters)

        return await self._get_paginated_quests(statement, filters, current_user=current_user)

    async def get_quests_on_moderation(self, filters: QuestListFilters) -> QuestPageResponse:
        return await self._get_paginated_quests(
            select(QuestModel)
            .options(
                selectinload(QuestModel.creator).selectinload(UserModel.team),
                selectinload(QuestModel.points),
            )
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
        quest = await self._get_quest(quest_id)
        best_map = await self._best_completion_seconds_by_quest_ids([quest.id])
        return self._quest_to_response(
            quest,
            best_completion_seconds=best_map.get(quest.id),
        )

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
            for complaint in complaints[offset: offset + limit]
        ]
        return QuestComplaintPageResponse(items=items, total=total, limit=limit, offset=offset)

    async def delete_complaint(self, complaint_id: int) -> None:
        complaint = await self._get_complaint(complaint_id)
        await self.session.delete(complaint)
        await self.session.commit()

    async def add_to_favorites(self, current_user: UserResponse, quest_id: int) -> None:
        quest = await self._get_quest(quest_id)
        if quest.status != QuestStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only published quests can be added to favorites",
            )

        existing = await self.session.execute(
            select(QuestFavoriteModel).where(
                QuestFavoriteModel.user_id == current_user.id,
                QuestFavoriteModel.quest_id == quest_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return

        self.session.add(QuestFavoriteModel(user_id=current_user.id, quest_id=quest_id))
        await self.session.commit()

    async def remove_from_favorites(self, current_user: UserResponse, quest_id: int) -> None:
        result = await self.session.execute(
            select(QuestFavoriteModel).where(
                QuestFavoriteModel.user_id == current_user.id,
                QuestFavoriteModel.quest_id == quest_id,
            )
        )
        favorite = result.scalar_one_or_none()
        if favorite is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest is not in favorites",
            )
        await self.session.delete(favorite)
        await self.session.commit()

    async def get_favorite_quests(
            self,
            current_user: UserResponse,
            filters: QuestListFilters,
    ) -> QuestPageResponse:
        statement = (
            select(QuestModel)
            .join(QuestFavoriteModel, QuestFavoriteModel.quest_id == QuestModel.id)
            .options(
                selectinload(QuestModel.creator).selectinload(UserModel.team),
                selectinload(QuestModel.points),
            )
            .where(
                QuestFavoriteModel.user_id == current_user.id,
                QuestModel.status == QuestStatus.PUBLISHED,
            )
            .order_by(QuestFavoriteModel.id.desc())
        )
        return await self._get_paginated_quests(statement, filters, current_user=current_user)

    async def _get_paginated_quests(
            self,
            statement,
            filters: QuestListFilters,
            *,
            current_user: UserResponse | None = None,
    ) -> QuestPageResponse:
        statement = self._apply_sql_filters(statement, filters)
        result = await self.session.execute(statement)
        quests = result.scalars().all()

        if filters.search:
            quests = [
                quest for quest in quests
                if self._matches_title_filter(quest.title, filters.search)
            ]

        if filters.city:
            quests = [
                quest for quest in quests
                if self._matches_city_filter(quest.location, filters.city)
            ]

        total = len(quests)
        start = filters.offset
        end = filters.offset + filters.limit
        page_quests = quests[start:end]
        favorite_ids: set[int] = set()
        completed_ids: set[int] = set()
        page_quest_ids = [q.id for q in page_quests]
        if current_user is not None and page_quest_ids:
            favorite_ids = await self._favourite_quest_ids(
                user_id=current_user.id,
                quest_ids=page_quest_ids,
            )
            completed_ids = await self._completed_quest_ids(
                user_id=current_user.id,
                quest_ids=page_quest_ids,
            )
        best_seconds_map = await self._best_completion_seconds_by_quest_ids(page_quest_ids)
        items = [
            self._quest_to_response(
                quest,
                is_favourite=quest.id in favorite_ids,
                is_completed=quest.id in completed_ids,
                best_completion_seconds=best_seconds_map.get(quest.id),
            )
            for quest in page_quests
        ]
        return QuestPageResponse(
            items=items,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    async def _get_quest(self, quest_id: int) -> QuestModel:
        result = await self.session.execute(
            select(QuestModel)
            .options(
                selectinload(QuestModel.creator).selectinload(UserModel.team),
                selectinload(QuestModel.points),
            )
            .where(QuestModel.id == quest_id)
        )
        quest = result.scalar_one_or_none()
        if quest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Quest not found",
            )
        return quest

    async def _get_quest_with_points(self, quest_id: int) -> QuestModel:
        result = await self.session.execute(
            select(QuestModel)
            .options(
                selectinload(QuestModel.creator).selectinload(UserModel.team),
                selectinload(QuestModel.points),
            )
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
        best_map = await self._best_completion_seconds_by_quest_ids([quest.id])
        return self._quest_to_response(
            quest,
            is_favourite=False,
            best_completion_seconds=best_map.get(quest.id),
        )

    async def _mark_exported_quest_completed(self, user_id: int, quest: QuestModel) -> None:
        points_count = len(self._sorted_points(quest))
        now = datetime.now(timezone.utc)

        active_result = await self.session.execute(
            select(QuestRunModel).where(
                QuestRunModel.user_id == user_id,
                QuestRunModel.quest_id == quest.id,
                QuestRunModel.status == QuestRunStatus.IN_PROGRESS,
            )
        )
        active_run = active_result.scalar_one_or_none()
        if active_run is not None:
            active_run.status = QuestRunStatus.COMPLETED
            active_run.completed_at = now
            active_run.current_step_index = points_count
            active_run.points_awarded = 0
            await self.session.commit()
            return

        completed_result = await self.session.execute(
            select(QuestRunModel.id)
            .where(
                QuestRunModel.user_id == user_id,
                QuestRunModel.quest_id == quest.id,
                QuestRunModel.status == QuestRunStatus.COMPLETED,
            )
            .limit(1)
        )
        if completed_result.scalar_one_or_none() is not None:
            return

        self.session.add(
            QuestRunModel(
                user_id=user_id,
                quest_id=quest.id,
                status=QuestRunStatus.COMPLETED,
                started_at=now,
                completed_at=now,
                current_step_index=points_count,
                points_awarded=0,
            )
        )
        await self.session.commit()

    @staticmethod
    def _sorted_points(quest: QuestModel) -> list[QuestPointModel]:
        return sorted(quest.points or [], key=lambda point: point.id)

    def _quest_to_response(
            self,
            quest: QuestModel,
            *,
            is_favourite: bool = False,
            is_completed: bool = False,
            best_completion_seconds: float | None = None,
    ) -> QuestResponse:
        try:
            return QuestResponse.from_quest_model(
                quest,
                is_favourite=is_favourite,
                is_completed=is_completed,
                best_completion_seconds=best_completion_seconds,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    async def _is_favourite(self, user_id: int, quest_id: int) -> bool:
        result = await self.session.execute(
            select(QuestFavoriteModel.id).where(
                QuestFavoriteModel.user_id == user_id,
                QuestFavoriteModel.quest_id == quest_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _is_completed(self, user_id: int, quest_id: int) -> bool:
        result = await self.session.execute(
            select(QuestRunModel.id)
            .where(
                QuestRunModel.user_id == user_id,
                QuestRunModel.quest_id == quest_id,
                QuestRunModel.status == QuestRunStatus.COMPLETED,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _favourite_quest_ids(self, user_id: int, quest_ids: list[int]) -> set[int]:
        if not quest_ids:
            return set()
        result = await self.session.execute(
            select(QuestFavoriteModel.quest_id).where(
                QuestFavoriteModel.user_id == user_id,
                QuestFavoriteModel.quest_id.in_(quest_ids),
            )
        )
        return set(result.scalars().all())

    async def _completed_quest_ids(self, user_id: int, quest_ids: list[int]) -> set[int]:
        if not quest_ids:
            return set()
        result = await self.session.execute(
            select(QuestRunModel.quest_id).where(
                QuestRunModel.user_id == user_id,
                QuestRunModel.quest_id.in_(quest_ids),
                QuestRunModel.status == QuestRunStatus.COMPLETED,
            )
        )
        return set(result.scalars().all())

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
        quest = await self._get_quest(quest_id)
        best_map = await self._best_completion_seconds_by_quest_ids([quest.id])
        return self._quest_to_response(
            quest,
            best_completion_seconds=best_map.get(quest.id),
        )

    async def _best_completion_seconds_by_quest_ids(self, quest_ids: list[int]) -> dict[int, float]:
        if not quest_ids:
            return {}
        elapsed_epoch = func.extract("epoch", QuestRunModel.completed_at - QuestRunModel.started_at)
        result = await self.session.execute(
            select(QuestRunModel.quest_id, func.min(elapsed_epoch))
            .where(
                QuestRunModel.quest_id.in_(quest_ids),
                QuestRunModel.status == QuestRunStatus.COMPLETED,
                QuestRunModel.completed_at.is_not(None),
            )
            .group_by(QuestRunModel.quest_id),
        )
        rows = result.all()
        out: dict[int, float] = {}
        for quest_id, seconds in rows:
            if seconds is None:
                continue
            out[quest_id] = float(seconds)
        return out

    @staticmethod
    def _ensure_creator(current_user: UserResponse, quest: QuestModel) -> None:
        if current_user.id != quest.creator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this quest",
            )

    @staticmethod
    def _apply_near_radius_filter(statement, filters: QuestListFilters):
        if filters.near_latitude is None or filters.near_longitude is None:
            return statement
        near_clause = text(
            """
            EXISTS (
              SELECT 1 FROM quest_points qp
              WHERE qp.quest_id = quests.id
              AND qp.id = (
                SELECT MIN(qp2.id) FROM quest_points qp2 WHERE qp2.quest_id = quests.id
              )
              AND ST_DWithin(
                ST_SetSRID(ST_MakePoint(qp.longitude, qp.latitude), 4326)::geography,
                ST_SetSRID(ST_MakePoint(:ref_lon, :ref_lat), 4326)::geography,
                :radius_m
              )
            )
            """
        ).bindparams(
            ref_lon=filters.near_longitude,
            ref_lat=filters.near_latitude,
            radius_m=NEAR_RADIUS_METERS,
        )
        return statement.where(near_clause)

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
        return cls._matches_text_filter(location, city)

    @classmethod
    def _matches_title_filter(cls, title: str, search: str) -> bool:
        return cls._matches_text_filter(title, search)

    @classmethod
    def _matches_text_filter(cls, value: str, query: str) -> bool:
        normalized_value = cls._normalize_text(value)
        normalized_query = cls._normalize_text(query)
        if not normalized_query:
            return True

        candidates = cls._text_match_candidates(normalized_value, normalized_query)
        if any(
                cls._is_partial_text_match(candidate, normalized_query)
                for candidate in candidates
        ):
            return True

        return any(
            cls._is_close_text_match(candidate, normalized_query)
            for candidate in candidates
        )

    @classmethod
    def _text_match_candidates(cls, normalized_value: str, normalized_query: str) -> set[str]:
        value_words = normalized_value.split()
        query_words_count = len(normalized_query.split())
        candidates = {normalized_value, *value_words}

        if query_words_count > 1:
            for window_size in range(
                    max(1, query_words_count - 1),
                    min(len(value_words), query_words_count + 1) + 1,
            ):
                candidates.update(cls._word_windows(value_words, window_size))

        return {candidate for candidate in candidates if candidate}

    @staticmethod
    def _word_windows(words: list[str], size: int) -> list[str]:
        return [
            " ".join(words[start: start + size])
            for start in range(0, len(words) - size + 1)
        ]

    @staticmethod
    def _is_partial_text_match(candidate: str, normalized_query: str) -> bool:
        if normalized_query in candidate:
            return True

        candidate_compact = candidate.replace(" ", "")
        query_compact = normalized_query.replace(" ", "")
        return bool(query_compact) and query_compact in candidate_compact

    @classmethod
    def _is_close_text_match(cls, candidate: str, normalized_query: str) -> bool:
        candidate_compact = candidate.replace(" ", "")
        query_compact = normalized_query.replace(" ", "")
        if not candidate_compact or not query_compact:
            return False

        query_length = len(query_compact)
        if abs(len(candidate_compact) - query_length) > cls._allowed_text_typos(query_length):
            return False

        if query_length <= 4 and candidate_compact[0] != query_compact[0]:
            return False

        ratio = SequenceMatcher(None, normalized_query, candidate).ratio()
        if ratio < cls._min_text_similarity(query_length):
            return False

        return cls._levenshtein_distance(candidate_compact, query_compact) <= cls._allowed_text_typos(query_length)

    @staticmethod
    def _allowed_text_typos(length: int) -> int:
        if length <= 4:
            return 1
        if length <= 8:
            return 1
        if length <= 14:
            return 2
        return 3

    @staticmethod
    def _min_text_similarity(length: int) -> float:
        if length <= 4:
            return 0.75
        if length <= 8:
            return 0.8
        if length <= 14:
            return 0.82
        return 0.84

    @staticmethod
    def _levenshtein_distance(left: str, right: str) -> int:
        if left == right:
            return 0
        if len(left) < len(right):
            left, right = right, left

        previous_row = list(range(len(right) + 1))
        for left_index, left_char in enumerate(left, start=1):
            current_row = [left_index]
            for right_index, right_char in enumerate(right, start=1):
                insertion = current_row[right_index - 1] + 1
                deletion = previous_row[right_index] + 1
                substitution = previous_row[right_index - 1] + (left_char != right_char)
                current_row.append(min(insertion, deletion, substitution))
            previous_row = current_row

        return previous_row[-1]

    @staticmethod
    def _normalize_text(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        value = ZERO_WIDTH_RE.sub("", value)
        value = value.casefold().replace("ё", "е")
        value = re.sub(r"[^a-zа-я0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value
