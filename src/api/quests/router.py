from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import UserResponse
from src.schemes.quests import (
    QuestArchiveStatusUpdateRequest,
    QuestComplaintCreateRequest,
    QuestComplaintResponse,
    QuestCreate,
    QuestDetailResponse,
    QuestListFilters,
    QuestPageResponse,
    QuestResponse,
)
from src.services.auth import get_current_user
from src.services.auth import get_current_user_optional
from src.services.quests import QuestService

router = APIRouter(tags=["Quests"], prefix="/quests")


@router.post("", response_model=QuestResponse, status_code=status.HTTP_201_CREATED)
async def create_quest(
    payload: QuestCreate = Depends(QuestCreate.as_form),
    image: UploadFile | None = File(default=None),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).create_quest(current_user, payload, image)


@router.get("", response_model=QuestPageResponse)
async def get_all_quests(
    filters: QuestListFilters = Depends(QuestListFilters.as_query),
    current_user: UserResponse | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(create_session),
) -> QuestPageResponse:
    return await QuestService(session).get_all_quests(filters, current_user)


@router.get("/my", response_model=QuestPageResponse)
async def get_my_quests(
    filters: QuestListFilters = Depends(QuestListFilters.as_query),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestPageResponse:
    return await QuestService(session).get_my_quests(current_user, filters)


@router.get("/favorites", response_model=QuestPageResponse)
async def get_favorite_quests(
    filters: QuestListFilters = Depends(QuestListFilters.as_query),
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestPageResponse:
    return await QuestService(session).get_favorite_quests(current_user, filters)


@router.get("/{quest_id}/export", response_class=Response)
async def export_quest_to_pdf(
    quest_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> Response:
    pdf_content = await QuestService(session).export_quest_to_pdf(current_user, quest_id)
    filename = f"quest-{quest_id}.pdf"
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{filename}\"; "
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.get("/{quest_id}", response_model=QuestDetailResponse)
async def get_quest(
    quest_id: int,
    current_user: UserResponse | None = Depends(get_current_user_optional),
    session: AsyncSession = Depends(create_session),
) -> QuestDetailResponse:
    return await QuestService(session).get_quest(quest_id, current_user)


@router.patch("/{quest_id}/status", response_model=QuestResponse)
async def update_my_quest_status(
    quest_id: int,
    payload: QuestArchiveStatusUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestResponse:
    return await QuestService(session).update_my_quest_archive_status(
        current_user=current_user,
        quest_id=quest_id,
        target_status=payload.status,
    )


@router.delete("/{quest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_quest(
    quest_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> None:
    await QuestService(session).delete_my_quest(current_user, quest_id)


@router.post("/{quest_id}/complaints", response_model=QuestComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_quest_complaint(
    quest_id: int,
    payload: QuestComplaintCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> QuestComplaintResponse:
    return await QuestService(session).create_complaint(current_user, quest_id, payload)


@router.post("/{quest_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def add_quest_to_favorites(
    quest_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> None:
    await QuestService(session).add_to_favorites(current_user, quest_id)


@router.delete("/{quest_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def remove_quest_from_favorites(
    quest_id: int,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
) -> None:
    await QuestService(session).remove_from_favorites(current_user, quest_id)
