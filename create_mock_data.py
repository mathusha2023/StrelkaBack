import argparse
import asyncio
import datetime
import logging

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.database.db_session import AsyncPostgresClient
from src.models.quest_complaints import QuestComplaintModel
from src.models.quest_favorites import QuestFavoriteModel
from src.models.quest_points import QuestPointModel
from src.models.quest_runs import QuestRunModel, QuestRunStatus
from src.models.quests import QuestModel, QuestStatus
from src.models.team_quest_runs import (
    TeamQuestRunCheckpointModel,
    TeamQuestRunModel,
    TeamQuestRunParticipantModel,
    TeamQuestRunStatus,
)
from src.models.teams import TeamModel
from src.models.users import UserModel, UserRole
from src.settings import settings


MOCK_EMAIL_PATTERN = "mock.%@example.com"
MOCK_QUEST_TITLE_PATTERN = "[MOCK]%"
MOCK_TEAM_CODE_PATTERN = "MOCK%"
DEFAULT_PASSWORD = "11111111"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create mock data for local development.")
    parser.add_argument(
        "--reset-mock",
        action="store_true",
        help="Delete previously created mock data before inserting it again.",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Password for all mock users. Defaults to {DEFAULT_PASSWORD!r}.",
    )
    return parser.parse_args()


async def mock_data_exists(session: AsyncSession) -> bool:
    result = await session.execute(
        select(UserModel.id).where(UserModel.email.like(MOCK_EMAIL_PATTERN)).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def delete_mock_data(session: AsyncSession) -> None:
    mock_user_ids = select(UserModel.id).where(UserModel.email.like(MOCK_EMAIL_PATTERN))
    mock_quest_ids = select(QuestModel.id).where(QuestModel.title.like(MOCK_QUEST_TITLE_PATTERN))
    mock_team_ids = select(TeamModel.id).where(TeamModel.code.like(MOCK_TEAM_CODE_PATTERN))
    mock_team_run_ids = select(TeamQuestRunModel.id).where(
        or_(
            TeamQuestRunModel.team_id.in_(mock_team_ids),
            TeamQuestRunModel.quest_id.in_(mock_quest_ids),
        )
    )

    await session.execute(
        delete(TeamQuestRunCheckpointModel).where(
            TeamQuestRunCheckpointModel.run_id.in_(mock_team_run_ids)
        )
    )
    await session.execute(
        delete(TeamQuestRunParticipantModel).where(
            TeamQuestRunParticipantModel.run_id.in_(mock_team_run_ids)
        )
    )
    await session.execute(
        delete(TeamQuestRunModel).where(TeamQuestRunModel.id.in_(mock_team_run_ids))
    )
    await session.execute(
        delete(QuestFavoriteModel).where(
            or_(
                QuestFavoriteModel.user_id.in_(mock_user_ids),
                QuestFavoriteModel.quest_id.in_(mock_quest_ids),
            )
        )
    )
    await session.execute(
        delete(QuestComplaintModel).where(
            or_(
                QuestComplaintModel.author_id.in_(mock_user_ids),
                QuestComplaintModel.quest_id.in_(mock_quest_ids),
            )
        )
    )
    await session.execute(
        delete(QuestRunModel).where(
            or_(
                QuestRunModel.user_id.in_(mock_user_ids),
                QuestRunModel.quest_id.in_(mock_quest_ids),
            )
        )
    )
    await session.execute(
        delete(QuestPointModel).where(QuestPointModel.quest_id.in_(mock_quest_ids))
    )
    await session.execute(delete(QuestModel).where(QuestModel.id.in_(mock_quest_ids)))
    await session.execute(
        update(UserModel)
        .where(UserModel.email.like(MOCK_EMAIL_PATTERN))
        .values(team_id=None)
    )
    await session.execute(delete(TeamModel).where(TeamModel.id.in_(mock_team_ids)))
    await session.execute(delete(UserModel).where(UserModel.id.in_(mock_user_ids)))


async def create_users(session: AsyncSession, password: str) -> list[UserModel]:
    hashed_password = hash_password(password)
    users = [
        UserModel(
            username="mock_moderator",
            email="mock.moderator@example.com",
            hashed_password=hashed_password,
            birthdate=datetime.date(1990, 5, 12),
            role=UserRole.MODERATOR,
            total_points=850,
        ),
        UserModel(
            username="mock_alisa",
            email="mock.alisa@example.com",
            hashed_password=hashed_password,
            birthdate=datetime.date(1998, 3, 4),
            total_points=320,
        ),
        UserModel(
            username="mock_boris",
            email="mock.boris@example.com",
            hashed_password=hashed_password,
            birthdate=datetime.date(1996, 8, 19),
            total_points=260,
        ),
        UserModel(
            username="mock_vika",
            email="mock.vika@example.com",
            hashed_password=hashed_password,
            birthdate=datetime.date(2001, 1, 22),
            total_points=410,
        ),
        UserModel(
            username="mock_denis",
            email="mock.denis@example.com",
            hashed_password=hashed_password,
            birthdate=datetime.date(1994, 11, 7),
            total_points=190,
        ),
        UserModel(
            username="mock_elena",
            email="mock.elena@example.com",
            hashed_password=hashed_password,
            birthdate=datetime.date(1999, 6, 30),
            total_points=530,
        ),
    ]
    session.add_all(users)
    await session.flush()
    return users


async def create_teams(session: AsyncSession, users: list[UserModel]) -> list[TeamModel]:
    teams = [
        TeamModel(
            name="Mock North Team",
            description="Тестовая команда для совместных прохождений.",
            code="MOCKNORTH1",
            creator_id=users[1].id,
        ),
        TeamModel(
            name="Mock River Team",
            description="Команда с завершенным командным квестом.",
            code="MOCKRIVER1",
            creator_id=users[3].id,
        ),
    ]
    session.add_all(teams)
    await session.flush()

    users[1].team_id = teams[0].id
    users[2].team_id = teams[0].id
    users[3].team_id = teams[1].id
    users[4].team_id = teams[1].id
    users[5].team_id = teams[1].id
    await session.flush()
    return teams


async def create_quests(session: AsyncSession, users: list[UserModel]) -> list[QuestModel]:
    quests = [
        QuestModel(
            title="[MOCK] Историческая прогулка",
            description="Небольшой маршрут по городским достопримечательностям.",
            location="Центр города",
            difficulty=2,
            duration_minutes=45,
            rules_and_warnings="Переходите дороги только по пешеходным переходам.",
            status=QuestStatus.PUBLISHED,
            creator_id=users[0].id,
        ),
        QuestModel(
            title="[MOCK] Набережная и мосты",
            description="Квест с заданиями около воды и видовых точек.",
            location="Набережная",
            difficulty=3,
            duration_minutes=70,
            rules_and_warnings="Одевайтесь по погоде.",
            status=QuestStatus.PUBLISHED,
            creator_id=users[1].id,
        ),
        QuestModel(
            title="[MOCK] Парковая головоломка",
            description="Маршрут для проверки командных механик.",
            location="Городской парк",
            difficulty=1,
            duration_minutes=30,
            status=QuestStatus.PUBLISHED,
            creator_id=users[3].id,
        ),
        QuestModel(
            title="[MOCK] Черновик на модерации",
            description="Квест для проверки модераторских сценариев.",
            location="Тестовая локация",
            difficulty=4,
            duration_minutes=90,
            status=QuestStatus.ON_MODERATION,
            creator_id=users[5].id,
        ),
    ]
    session.add_all(quests)
    await session.flush()
    return quests


async def create_quest_points(
    session: AsyncSession,
    quests: list[QuestModel],
) -> dict[int, list[QuestPointModel]]:
    points_by_quest: dict[int, list[QuestPointModel]] = {}
    point_specs = {
        quests[0].id: [
            ("Старая арка", 55.751244, 37.618423, "Сколько колонн у арки?", "4"),
            ("Площадь", 55.753930, 37.620795, "Какой год указан на табличке?", "1912"),
            ("Финальная точка", 55.755826, 37.617300, "Введите слово с памятника.", "старт"),
        ],
        quests[1].id: [
            ("Смотровая", 55.748900, 37.590100, "Сколько фонарей рядом?", "6"),
            ("Мост", 55.746700, 37.584400, "Какого цвета перила?", "зеленый"),
            ("Причал", 55.744200, 37.580500, "Номер ближайшего причала?", "3"),
        ],
        quests[2].id: [
            ("Вход в парк", 55.761100, 37.602200, "Найдите первую букву на схеме.", "п"),
            ("Фонтан", 55.762000, 37.604500, "Сколько чаш у фонтана?", "2"),
            ("Беседка", 55.763300, 37.606100, "Какой символ на крыше?", "звезда"),
        ],
        quests[3].id: [
            ("Тестовая точка", 55.700000, 37.600000, "Ответ для модерации?", "мок"),
        ],
    }

    for quest_id, specs in point_specs.items():
        points_by_quest[quest_id] = []
        for title, latitude, longitude, task, answer in specs:
            point = QuestPointModel(
                title=title,
                latitude=latitude,
                longitude=longitude,
                task=task,
                correct_answer=answer,
                hint="Это подсказка для мокового задания.",
                point_rules="Ответ вводится строчными буквами.",
                quest_id=quest_id,
            )
            points_by_quest[quest_id].append(point)
            session.add(point)

    await session.flush()
    return points_by_quest


async def create_activity(
    session: AsyncSession,
    users: list[UserModel],
    teams: list[TeamModel],
    quests: list[QuestModel],
    points_by_quest: dict[int, list[QuestPointModel]],
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    session.add_all(
        [
            QuestFavoriteModel(user_id=users[1].id, quest_id=quests[0].id),
            QuestFavoriteModel(user_id=users[2].id, quest_id=quests[1].id),
            QuestFavoriteModel(user_id=users[4].id, quest_id=quests[2].id),
            QuestComplaintModel(
                author_id=users[2].id,
                quest_id=quests[3].id,
                reason="Моковая жалоба для проверки модерации.",
            ),
            QuestRunModel(
                user_id=users[1].id,
                quest_id=quests[0].id,
                status=QuestRunStatus.COMPLETED,
                started_at=now - datetime.timedelta(days=3, hours=2),
                completed_at=now - datetime.timedelta(days=3, hours=1),
                current_step_index=len(points_by_quest[quests[0].id]),
                points_awarded=120,
            ),
            QuestRunModel(
                user_id=users[2].id,
                quest_id=quests[1].id,
                status=QuestRunStatus.IN_PROGRESS,
                started_at=now - datetime.timedelta(minutes=25),
                current_step_index=1,
            ),
            QuestRunModel(
                user_id=users[5].id,
                quest_id=quests[2].id,
                status=QuestRunStatus.COMPLETED,
                started_at=now - datetime.timedelta(days=1, hours=4),
                completed_at=now - datetime.timedelta(days=1, hours=3),
                current_step_index=len(points_by_quest[quests[2].id]),
                points_awarded=90,
            ),
        ]
    )

    active_team_run = TeamQuestRunModel(
        team_id=teams[0].id,
        quest_id=quests[1].id,
        status=TeamQuestRunStatus.IN_PROGRESS,
        starts_at=now - datetime.timedelta(minutes=10),
        started_at=now - datetime.timedelta(minutes=10),
    )
    completed_team_run = TeamQuestRunModel(
        team_id=teams[1].id,
        quest_id=quests[2].id,
        status=TeamQuestRunStatus.COMPLETED,
        starts_at=now - datetime.timedelta(days=2, hours=1),
        started_at=now - datetime.timedelta(days=2, hours=1),
        completed_at=now - datetime.timedelta(days=2),
        points_awarded=270,
    )
    session.add_all([active_team_run, completed_team_run])
    await session.flush()

    session.add_all(
        [
            TeamQuestRunParticipantModel(
                run_id=active_team_run.id,
                user_id=users[1].id,
                ready_at=now - datetime.timedelta(minutes=12),
            ),
            TeamQuestRunParticipantModel(
                run_id=active_team_run.id,
                user_id=users[2].id,
                ready_at=now - datetime.timedelta(minutes=11),
            ),
            TeamQuestRunParticipantModel(
                run_id=completed_team_run.id,
                user_id=users[3].id,
                ready_at=now - datetime.timedelta(days=2, hours=1, minutes=5),
            ),
            TeamQuestRunParticipantModel(
                run_id=completed_team_run.id,
                user_id=users[4].id,
                ready_at=now - datetime.timedelta(days=2, hours=1, minutes=4),
            ),
            TeamQuestRunParticipantModel(
                run_id=completed_team_run.id,
                user_id=users[5].id,
                ready_at=now - datetime.timedelta(days=2, hours=1, minutes=3),
            ),
        ]
    )

    active_points = points_by_quest[quests[1].id]
    completed_points = points_by_quest[quests[2].id]
    session.add(
        TeamQuestRunCheckpointModel(
            run_id=active_team_run.id,
            quest_point_id=active_points[0].id,
            completed_by_user_id=users[1].id,
            completed_at=now - datetime.timedelta(minutes=4),
        )
    )
    session.add_all(
        [
            TeamQuestRunCheckpointModel(
                run_id=completed_team_run.id,
                quest_point_id=point.id,
                completed_by_user_id=users[3 + index % 3].id,
                completed_at=now - datetime.timedelta(days=2, minutes=20 - index * 5),
            )
            for index, point in enumerate(completed_points)
        ]
    )


async def seed_mock_data(session: AsyncSession, password: str) -> None:
    users = await create_users(session, password)
    teams = await create_teams(session, users)
    quests = await create_quests(session, users)
    points_by_quest = await create_quest_points(session, quests)
    await create_activity(session, users, teams, quests, points_by_quest)


async def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO)

    await AsyncPostgresClient.init_postgres(settings.postgres_url)
    session_maker = AsyncPostgresClient.get_async_session()

    try:
        async with session_maker() as session:
            if args.reset_mock:
                await delete_mock_data(session)
                await session.commit()
                print("Deleted existing mock data.")
            elif await mock_data_exists(session):
                print("Mock data already exists. Use --reset-mock to recreate it.")
                return

            await seed_mock_data(session, args.password)
            await session.commit()

        print("Mock data created successfully.")
        print(f"Mock users password: {args.password}")
    finally:
        await AsyncPostgresClient.close_postgres()


if __name__ == "__main__":
    asyncio.run(main())
