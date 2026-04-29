"""Демо-данные для жюри: Смоленск + Нижний Новгород.

Идемпотентен: при повторном запуске удаляет всё, что относится к демо-набору
(определяется по email пользователей и тайтлам квестов из этого файла) и создаёт заново.

Запуск:
    docker compose exec api python scripts/seed_demo.py

или локально (если переменные окружения смотрят на доступную БД):
    python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.security import hash_password
from src.database.base import Base
from src.models import (
    AchievementModel,
    QuestComplaintModel,
    QuestFavoriteModel,
    QuestModel,
    QuestPointModel,
    QuestRunModel,
    TeamModel,
    TeamQuestRunCheckpointModel,
    TeamQuestRunModel,
    TeamQuestRunParticipantModel,
    UserAchievementModel,
    UserModel,
)
from src.models.achievements import AchievementCriteria
from src.models.quest_runs import QuestRunStatus
from src.models.quests import QuestStatus
from src.models.team_quest_runs import TeamQuestRunStatus
from src.models.users import UserRole
from src.services.achievements import load_default_achievements
from src.settings import settings

logger = logging.getLogger("seed_demo")

UTC = timezone.utc
NOW = datetime.now(UTC).replace(microsecond=0)


# ---------------------------------------------------------------------------
# Пользователи: 1 модератор + 10 игроков (возраст 14–17)
# ---------------------------------------------------------------------------

DEMO_PASSWORD = "demo1234"  # min_length=8 в LoginRequest; брифовое "demo123" не проходит валидацию


USERS: list[dict] = [
    # Модератор для жюри
    {
        "key": "moderator",
        "username": "moderator",
        "email": "moderator@strelka.ru",
        "password": DEMO_PASSWORD,
        "birthdate": date(1995, 3, 12),
        "role": UserRole.MODERATOR,
    },
    # Команда «Стрелки Новгорода»
    {
        "key": "ivan",
        "username": "ivan_volgar",
        "email": "ivan.surkov@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2009, 5, 14),  # 16 лет
        "role": UserRole.USER,
    },
    {
        "key": "anna",
        "username": "anya_pkv",
        "email": "anna.polyakova@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2010, 8, 2),  # 15 лет
        "role": UserRole.USER,
    },
    {
        "key": "dmitry",
        "username": "kovalchuk.d",
        "email": "dmitry.kovalchuk@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2009, 11, 23),  # 16 лет
        "role": UserRole.USER,
    },
    {
        "key": "maria",
        "username": "masha_lebedeva",
        "email": "maria.lebedeva@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2011, 2, 9),  # 15 лет
        "role": UserRole.USER,
    },
    # Команда «Смоленские Соколы»
    {
        "key": "artem",
        "username": "artem_zotov",
        "email": "artem.zotov@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2008, 6, 18),  # 17 лет
        "role": UserRole.USER,
    },
    {
        "key": "sofya",
        "username": "sofi_g",
        "email": "sofya.gromova@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2009, 1, 30),  # 17 лет
        "role": UserRole.USER,
    },
    {
        "key": "nikita",
        "username": "n.zhukov",
        "email": "nikita.zhukov@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2010, 9, 4),  # 15 лет
        "role": UserRole.USER,
    },
    # Команда «Поволжские Лисы»
    {
        "key": "polina",
        "username": "polly_sed",
        "email": "polina.sedova@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2010, 12, 11),  # 15 лет
        "role": UserRole.USER,
    },
    {
        "key": "timofey",
        "username": "tim_orlov",
        "email": "timofey.orlov@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2011, 7, 21),  # 14 лет
        "role": UserRole.USER,
    },
    # Соло-игрок (без команды)
    {
        "key": "alisa",
        "username": "alisa_z",
        "email": "alisa.zaitseva@example.com",
        "password": DEMO_PASSWORD,
        "birthdate": date(2009, 4, 3),  # 17 лет (соло)
        "role": UserRole.USER,
    },
]

# ---------------------------------------------------------------------------
# Команды (создатель + участники)
# ---------------------------------------------------------------------------

TEAMS: list[dict] = [
    {
        "name": "Стрелки Новгорода",
        "description": (
            "Команда из Нижнего: ходим по Покровке, лазаем на Чкаловскую и "
            "знаем все башни Кремля наизусть."
        ),
        "code": "STR2026NN001",
        "creator_key": "ivan",
        "member_keys": ["ivan", "anna", "dmitry", "maria"],
    },
    {
        "name": "Смоленские Соколы",
        "description": (
            "Любим старые крепости и тихие смоленские дворы. "
            "Готовы к длинным маршрутам по холмам над Днепром."
        ),
        "code": "SOK2026SML01",
        "creator_key": "artem",
        "member_keys": ["artem", "sofya", "nikita"],
    },
    {
        "name": "Поволжские Лисы",
        "description": (
            "Маленькая, но шустрая команда. Любим городские тайны и квесты "
            "на скорость."
        ),
        "code": "FOX2026VLG01",
        "creator_key": "polina",
        "member_keys": ["polina", "timofey"],
    },
]

# ---------------------------------------------------------------------------
# Квесты: 6 в Смоленске, 6 в Нижнем Новгороде. Реальные локации.
# Статусы: 9 published, 1 on_moderation, 1 rejected, 1 archived.
# ---------------------------------------------------------------------------

QUESTS: list[dict] = [
    # ============ СМОЛЕНСК ============
    {
        "key": "kremlin_smolensk",
        "title": "Стены крепости-героя",
        "description": (
            "Большой пеший маршрут по уцелевшим башням Смоленской крепостной "
            "стены — одного из крупнейших оборонительных сооружений Европы. "
            "По дороге узнаете, как город держал осаду в 1609–1611 годах."
        ),
        "location": "Смоленск, Центральный район",
        "difficulty": 3,
        "duration_minutes": 90,
        "rules_and_warnings": (
            "Пройдите маршрут только в светлое время суток. "
            "Не забирайтесь на полуразрушенные участки стены."
        ),
        "status": QuestStatus.PUBLISHED,
        "creator_key": "artem",
        "points": [
            {
                "title": "Громовая башня",
                "latitude": 54.7820,
                "longitude": 32.0428,
                "task": (
                    "Найдите информационную табличку рядом с башней. "
                    "Назовите однословное прозвище башни, которое дано ей за форму вершины."
                ),
                "correct_answer": "громовая",
                "hint": "Прозвище совпадает с названием грозного природного явления.",
                "point_rules": "Не выходите на проезжую часть улицы Дзержинского.",
            },
            {
                "title": "Никольские ворота",
                "latitude": 54.7821,
                "longitude": 32.0467,
                "task": (
                    "Через эти ворота шли войска в осаждённый город. "
                    "Как одним словом называется проезд внутри башни-ворот?"
                ),
                "correct_answer": "арка",
                "hint": "Полукруглый каменный свод над проездом.",
                "point_rules": None,
            },
            {
                "title": "Пятницкая башня",
                "latitude": 54.7898,
                "longitude": 32.0431,
                "task": (
                    "Башня названа по имени церкви, стоявшей рядом. "
                    "Введите название дня недели, в честь которого она названа."
                ),
                "correct_answer": "пятница",
                "hint": "Покровительница торговли — святая Параскева.",
                "point_rules": "Двигайтесь по тротуару, мимо проезжают самосвалы.",
            },
            {
                "title": "Башня Веселуха",
                "latitude": 54.7917,
                "longitude": 32.0578,
                "task": (
                    "Полное «парадное» имя башни — это форма Софийской. "
                    "Введите название реки, которую видно с её площадки."
                ),
                "correct_answer": "днепр",
                "hint": "Главная река Смоленска.",
                "point_rules": "Не подходите к обрыву ближе чем на 2 метра.",
            },
        ],
    },
    {
        "key": "literary_smolensk",
        "title": "Литературные тропы Смоленска",
        "description": (
            "Прогулка по местам, связанным с Глинкой, Твардовским и Тенишевой. "
            "Узнаете, где композитор слушал народные песни, а поэт писал «Тёркина»."
        ),
        "location": "Смоленск, сад Блонье и окрестности",
        "difficulty": 2,
        "duration_minutes": 60,
        "rules_and_warnings": "Маршрут полностью пешеходный, удобен для младших подростков.",
        "status": QuestStatus.PUBLISHED,
        "creator_key": "sofya",
        "points": [
            {
                "title": "Памятник М. И. Глинке",
                "latitude": 54.7855,
                "longitude": 32.0494,
                "task": (
                    "На постаменте памятника композитору указан год его рождения. "
                    "Введите год четырьмя цифрами."
                ),
                "correct_answer": "1804",
                "hint": "Композитор родился в начале XIX века.",
                "point_rules": "Не залезайте на постамент.",
            },
            {
                "title": "Сад Блонье",
                "latitude": 54.7853,
                "longitude": 32.0492,
                "task": (
                    "В саду стоит фонтан со скульптурой животного из сказки. "
                    "Назовите это животное одним словом."
                ),
                "correct_answer": "олень",
                "hint": "Бронзовый, с ветвистыми рогами — символ парка.",
                "point_rules": None,
            },
            {
                "title": "Памятник А. Т. Твардовскому и Василию Тёркину",
                "latitude": 54.7806,
                "longitude": 32.0466,
                "task": (
                    "Скульптурная композиция изображает поэта и его героя. "
                    "Введите имя главного героя поэмы Твардовского."
                ),
                "correct_answer": "василий",
                "hint": "«Свой парень» с гармонью.",
                "point_rules": None,
            },
        ],
    },
    {
        "key": "memory_smolensk",
        "title": "Огонь, посвящённый памяти",
        "description": (
            "Короткий маршрут по сквру Памяти Героев у крепостной стены. "
            "Подходит для младших подростков и первого знакомства с городом."
        ),
        "location": "Смоленск, сквер Памяти Героев",
        "difficulty": 1,
        "duration_minutes": 40,
        "rules_and_warnings": "Соблюдайте тишину у Вечного огня.",
        # Этот квест отклонён модератором — пример работы модерации
        "status": QuestStatus.REJECTED,
        "rejection_reason": (
            "В тексте задания упоминался спуск к насыпи у железной дороги. "
            "Пожалуйста, уберите небезопасные участки и отправьте на повторную модерацию."
        ),
        "creator_key": "nikita",
        "points": [
            {
                "title": "Сквер Памяти Героев",
                "latitude": 54.7847,
                "longitude": 32.0469,
                "task": (
                    "Найдите центральную аллею сквера. "
                    "Сколько слов из двух букв в слове на табличке у входа? Введите цифрой."
                ),
                "correct_answer": "0",
                "hint": "Считайте только короткие слова на самой табличке.",
                "point_rules": None,
            },
            {
                "title": "Вечный огонь",
                "latitude": 54.7849,
                "longitude": 32.0468,
                "task": (
                    "На плите рядом с огнём указан год окончания Великой "
                    "Отечественной войны. Введите его четырьмя цифрами."
                ),
                "correct_answer": "1945",
                "hint": "Год Победы.",
                "point_rules": "Подходите к огню только с подветренной стороны.",
            },
            {
                "title": "Аллея Героев",
                "latitude": 54.7847,
                "longitude": 32.0466,
                "task": (
                    "Пройдитесь по аллее. Введите название дерева, которое "
                    "высажено вдоль всей аллеи."
                ),
                "correct_answer": "липа",
                "hint": "Цветёт в июне, сладко пахнет.",
                "point_rules": None,
            },
        ],
    },
    {
        "key": "ancient_heart",
        "title": "Древнее сердце Смоленска",
        "description": (
            "Маршрут по самым старым храмам города: Успенскому собору и "
            "церквам домонгольской поры. Поход для тех, кто любит историю и "
            "готов подниматься по крутым улочкам."
        ),
        "location": "Смоленск, Соборная гора и Заднепровье",
        "difficulty": 4,
        "duration_minutes": 120,
        "rules_and_warnings": (
            "В храмах действует дресс-код, без шорт. "
            "Будьте внимательны — рельеф города холмистый."
        ),
        "status": QuestStatus.PUBLISHED,
        "creator_key": "artem",
        "points": [
            {
                "title": "Успенский собор",
                "latitude": 54.7861,
                "longitude": 32.0561,
                "task": (
                    "Поднимитесь к собору. На какой по счёту холм Смоленска "
                    "вы поднялись? Введите число."
                ),
                "correct_answer": "1",
                "hint": "Это самая возвышенная точка исторического центра.",
                "point_rules": "Не входите в храм во время службы.",
            },
            {
                "title": "Церковь Петра и Павла",
                "latitude": 54.7896,
                "longitude": 32.0306,
                "task": (
                    "Это один из трёх сохранившихся домонгольских храмов города. "
                    "Назовите век, в котором она построена (римскими цифрами)."
                ),
                "correct_answer": "xii",
                "hint": "Двенадцатый век.",
                "point_rules": None,
            },
            {
                "title": "Свирская церковь",
                "latitude": 54.7733,
                "longitude": 32.0114,
                "task": (
                    "Найдите рядом с церковью камень-валун. "
                    "Введите название реки, на берегу которой стоит храм."
                ),
                "correct_answer": "днепр",
                "hint": "Главная река Смоленска.",
                "point_rules": "Не сходите с тропинки на склон.",
            },
            {
                "title": "Церковь Иоанна Богослова",
                "latitude": 54.7864,
                "longitude": 32.0254,
                "task": (
                    "Введите имя князя, при котором построен этот храм "
                    "(одно слово, в именительном падеже)."
                ),
                "correct_answer": "роман",
                "hint": "Роман Ростиславич, конец XII века.",
                "point_rules": None,
            },
        ],
    },
    {
        "key": "dnieper_sunset",
        "title": "Закат у Днепра",
        "description": (
            "Спокойный вечерний маршрут по набережной с видами на крепостную стену. "
            "Идеально подходит для лёгкой прогулки и фотографий заката."
        ),
        "location": "Смоленск, Набережная",
        "difficulty": 2,
        "duration_minutes": 50,
        "rules_and_warnings": "Маршрут планируется на закате — берите фонарик.",
        # На модерации
        "status": QuestStatus.ON_MODERATION,
        "creator_key": "sofya",
        "points": [
            {
                "title": "Спуск на набережную",
                "latitude": 54.7906,
                "longitude": 32.0507,
                "task": (
                    "Сосчитайте количество фонарных столбов на верхнем ярусе "
                    "от лестницы до памятника. Введите число."
                ),
                "correct_answer": "12",
                "hint": "Считайте только большие столбы со светильниками.",
                "point_rules": "Двигайтесь по тротуару, не сходите на проезжую часть.",
            },
            {
                "title": "Памятник Владимиру Крестителю",
                "latitude": 54.7910,
                "longitude": 32.0525,
                "task": (
                    "На постаменте указан год крещения Руси. "
                    "Введите его четырьмя цифрами."
                ),
                "correct_answer": "988",
                "hint": "Конец X века.",
                "point_rules": None,
            },
            {
                "title": "Башня Орёл",
                "latitude": 54.7902,
                "longitude": 32.0606,
                "task": (
                    "Подойдите к башне со стороны набережной. "
                    "Введите название птицы, давшей имя башне."
                ),
                "correct_answer": "орёл",
                "hint": "Гордая хищная птица — символ многих гербов.",
                "point_rules": None,
            },
        ],
    },
    {
        "key": "blonye_secrets",
        "title": "Секреты сада Блонье",
        "description": (
            "Семейный квест по саду Блонье — сердцу прогулочного Смоленска. "
            "Ищите спрятанные детали скульптур и редкие деревья."
        ),
        "location": "Смоленск, сад Блонье",
        "difficulty": 1,
        "duration_minutes": 35,
        "rules_and_warnings": "Не сходите с дорожек на газон.",
        "status": QuestStatus.PUBLISHED,
        "creator_key": "sofya",
        "points": [
            {
                "title": "Главная аллея",
                "latitude": 54.7857,
                "longitude": 32.0488,
                "task": (
                    "Сколько фонарей-«одуванчиков» вы насчитаете вдоль "
                    "главной аллеи? Введите цифрой."
                ),
                "correct_answer": "8",
                "hint": "Шарообразные плафоны на чугунных столбах.",
                "point_rules": None,
            },
            {
                "title": "Бронзовый олень",
                "latitude": 54.7853,
                "longitude": 32.0492,
                "task": (
                    "На рога оленя, по легенде, нужно загадать желание. "
                    "Сколько у фигуры рогов-отростков на правом роге? Введите число."
                ),
                "correct_answer": "5",
                "hint": "Считайте все ответвления.",
                "point_rules": "Не залезайте на скульптуру.",
            },
            {
                "title": "Эстрада-ракушка",
                "latitude": 54.7858,
                "longitude": 32.0497,
                "task": (
                    "Введите слово на табличке возле эстрады, описывающее "
                    "форму её крыши."
                ),
                "correct_answer": "ракушка",
                "hint": "Морское существо в раковине.",
                "point_rules": None,
            },
        ],
    },
    # ============ НИЖНИЙ НОВГОРОД ============
    {
        "key": "strelka_volga",
        "title": "Стрелка над Волгой",
        "description": (
            "Большой пеший маршрут на стрелку Оки и Волги — точку, ради "
            "которой Нижний называют столицей рек. Финал у стадиона ЧМ-2018."
        ),
        "location": "Нижний Новгород, Канавинский район",
        "difficulty": 3,
        "duration_minutes": 80,
        "rules_and_warnings": (
            "На набережной бывает сильный ветер. Возьмите ветровку. "
            "Маршрут плоский — подойдёт даже после большой школьной пары."
        ),
        "status": QuestStatus.PUBLISHED,
        "creator_key": "ivan",
        "points": [
            {
                "title": "Стадион «Нижний Новгород»",
                "latitude": 56.3367,
                "longitude": 43.9504,
                "task": (
                    "На фасаде стадиона выведен год постройки. "
                    "Введите его четырьмя цифрами."
                ),
                "correct_answer": "2018",
                "hint": "Год чемпионата мира по футболу в России.",
                "point_rules": "Не подходите к служебным воротам стадиона.",
            },
            {
                "title": "Собор Александра Невского",
                "latitude": 56.3350,
                "longitude": 43.9605,
                "task": (
                    "Сколько куполов у собора, считая центральный? "
                    "Введите цифрой."
                ),
                "correct_answer": "5",
                "hint": "Стандартное число для крупного православного храма.",
                "point_rules": "Не пользуйтесь вспышкой при службе.",
            },
            {
                "title": "Стрелка Оки и Волги",
                "latitude": 56.3370,
                "longitude": 43.9594,
                "task": (
                    "Введите название реки, которая впадает здесь в Волгу."
                ),
                "correct_answer": "ока",
                "hint": "Главный приток Волги в этой точке.",
                "point_rules": "Не подходите к самой кромке воды без сопровождения.",
            },
            {
                "title": "Канавинский мост",
                "latitude": 56.3322,
                "longitude": 43.9663,
                "task": (
                    "Сколько арок у Канавинского моста? Введите число."
                ),
                "correct_answer": "5",
                "hint": "Считайте только большие речные пролёты.",
                "point_rules": "Двигайтесь только по пешеходной части.",
            },
        ],
    },
    {
        "key": "pokrovskaya_walk",
        "title": "Большая Покровская: пешеходный маршрут",
        "description": (
            "Прогулка по главной пешеходной улице Нижнего. Памятник Козе, "
            "Дворник, Театр драмы и площадь Горького — всё здесь."
        ),
        "location": "Нижний Новгород, Большая Покровская",
        "difficulty": 2,
        "duration_minutes": 60,
        "rules_and_warnings": "На улице много велокурьеров — будьте внимательны.",
        "status": QuestStatus.PUBLISHED,
        "creator_key": "anna",
        "points": [
            {
                "title": "Площадь Минина и Пожарского",
                "latitude": 56.3270,
                "longitude": 43.9941,
                "task": (
                    "Введите фамилию посадского старосты, чьё имя носит площадь."
                ),
                "correct_answer": "минин",
                "hint": "Кузьма, поднявший ополчение в 1611 году.",
                "point_rules": None,
            },
            {
                "title": "Памятник Дворнику",
                "latitude": 56.3253,
                "longitude": 43.9935,
                "task": (
                    "В руках у бронзового дворника один инструмент. "
                    "Назовите его одним словом."
                ),
                "correct_answer": "метла",
                "hint": "Связка прутьев на длинной ручке.",
                "point_rules": None,
            },
            {
                "title": "Театр драмы",
                "latitude": 56.3267,
                "longitude": 43.9945,
                "task": (
                    "На фасаде указано имя писателя, в честь которого "
                    "назван театр. Введите его фамилию."
                ),
                "correct_answer": "горький",
                "hint": "Автор «На дне» родился в Нижнем.",
                "point_rules": None,
            },
            {
                "title": "Памятник Козе",
                "latitude": 56.3231,
                "longitude": 43.9925,
                "task": (
                    "Коза — символ нижегородского герба XV века. "
                    "Введите слово, которое чаще всего загадывают, потирая её рог."
                ),
                "correct_answer": "удача",
                "hint": "Это не «деньги» и не «любовь».",
                "point_rules": "Не сидите на скульптуре долго — за вами очередь.",
            },
            {
                "title": "Площадь Горького",
                "latitude": 56.3199,
                "longitude": 43.9882,
                "task": (
                    "На постаменте памятника указан год рождения Горького. "
                    "Введите его четырьмя цифрами."
                ),
                "correct_answer": "1868",
                "hint": "Середина XIX века.",
                "point_rules": None,
            },
        ],
    },
    {
        "key": "kremlin_nn",
        "title": "Кремлёвские башни",
        "description": (
            "Подробный маршрут по нижегородскому Кремлю: пять башен, "
            "обзорные площадки и виды на Волгу. Подойдёт для активной группы."
        ),
        "location": "Нижний Новгород, Кремль",
        "difficulty": 3,
        "duration_minutes": 90,
        "rules_and_warnings": (
            "В Кремле много ступеней — наденьте удобную обувь. "
            "На стенах не свешивайтесь за парапеты."
        ),
        "status": QuestStatus.PUBLISHED,
        "creator_key": "dmitry",
        "points": [
            {
                "title": "Дмитриевская башня",
                "latitude": 56.3286,
                "longitude": 43.9999,
                "task": (
                    "Главная башня выходит на площадь. "
                    "Введите имя князя, в честь которого она названа."
                ),
                "correct_answer": "дмитрий",
                "hint": "Дмитрий Константинович, XIV век.",
                "point_rules": None,
            },
            {
                "title": "Часовая башня",
                "latitude": 56.3306,
                "longitude": 44.0028,
                "task": (
                    "Назовите количество стрелок на часах башни. Введите число."
                ),
                "correct_answer": "2",
                "hint": "Часовая и минутная.",
                "point_rules": "Не подходите к краю обрыва за башней.",
            },
            {
                "title": "Тайницкая башня",
                "latitude": 56.3299,
                "longitude": 43.9959,
                "task": (
                    "Башня названа по тайному ходу. К чему вёл этот ход? "
                    "Введите одно слово — куда?"
                ),
                "correct_answer": "вода",
                "hint": "Этот ресурс был критически важен при осаде.",
                "point_rules": None,
            },
            {
                "title": "Никольская башня",
                "latitude": 56.3309,
                "longitude": 43.9969,
                "task": (
                    "У башни стоит современный пешеходный мост. "
                    "Назовите цвет его перильных ограждений (одно слово)."
                ),
                "correct_answer": "красный",
                "hint": "Цвет, ассоциирующийся с праздником.",
                "point_rules": "Двигайтесь по правой стороне моста.",
            },
            {
                "title": "Ивановская башня",
                "latitude": 56.3275,
                "longitude": 44.0050,
                "task": (
                    "Через эту башню в 1612 году выходило ополчение Минина "
                    "и Пожарского. Введите фамилию воеводы (Дмитрий ...)."
                ),
                "correct_answer": "пожарский",
                "hint": "Князь Дмитрий Михайлович.",
                "point_rules": None,
            },
        ],
    },
    {
        "key": "cable_car",
        "title": "Подъём над городом: канатная дорога",
        "description": (
            "Маршрут с поездкой через Волгу на канатной дороге Нижний — Бор. "
            "Высота над рекой — до 82 метров. Подойдёт самым смелым."
        ),
        "location": "Нижний Новгород, нижняя станция канатки",
        "difficulty": 4,
        "duration_minutes": 70,
        "rules_and_warnings": (
            "Прокат канатной дороги стоит около 150₽ в одну сторону — "
            "учитывайте это перед стартом."
        ),
        "status": QuestStatus.PUBLISHED,
        "creator_key": "maria",
        "points": [
            {
                "title": "Сенная площадь",
                "latitude": 56.3208,
                "longitude": 44.0264,
                "task": (
                    "Введите название одного из исторических товаров, "
                    "которыми торговали на этой площади (одно слово)."
                ),
                "correct_answer": "сено",
                "hint": "Подсказка зашита в самом названии площади.",
                "point_rules": None,
            },
            {
                "title": "Нижняя станция канатки",
                "latitude": 56.3214,
                "longitude": 44.0231,
                "task": (
                    "Сколько кабинок одновременно ходит между станциями? "
                    "Введите число (точная цифра указана на инфо-стенде)."
                ),
                "correct_answer": "28",
                "hint": "Двузначное число, чуть больше 25.",
                "point_rules": "Не выходите за ограждение зоны посадки.",
            },
            {
                "title": "Станция Бор",
                "latitude": 56.3568,
                "longitude": 44.0697,
                "task": (
                    "На станции Бор есть смотровая площадка. "
                    "Введите название города, в который вы прибыли."
                ),
                "correct_answer": "бор",
                "hint": "Совпадает с названием хвойного леса.",
                "point_rules": "Возвращайтесь на ту же станцию для обратного билета.",
            },
        ],
    },
    {
        "key": "chkalov_stairs",
        "title": "Чкаловская лестница: 560 ступеней",
        "description": (
            "Спортивный квест: пройти Чкаловскую лестницу сверху вниз и "
            "обратно, отвечая на вопросы по дороге. Только для подготовленных."
        ),
        "location": "Нижний Новгород, верхняя Волжская набережная",
        "difficulty": 5,
        "duration_minutes": 45,
        "rules_and_warnings": (
            "Перед стартом разомните икры. "
            "Не бегите по лестнице — ступени каменные и скользят после дождя."
        ),
        "status": QuestStatus.PUBLISHED,
        "creator_key": "ivan",
        "points": [
            {
                "title": "Памятник Чкалову",
                "latitude": 56.3293,
                "longitude": 44.0094,
                "task": (
                    "В каком году совершён беспосадочный перелёт Чкалова "
                    "через Северный полюс? Введите год."
                ),
                "correct_answer": "1937",
                "hint": "Конец 1930-х.",
                "point_rules": "Не залезайте на постамент памятника.",
            },
            {
                "title": "Середина лестницы",
                "latitude": 56.3302,
                "longitude": 44.0096,
                "task": (
                    "Сколько ступеней насчитывает Чкаловская лестница, "
                    "если идти только по одной её стороне? Введите число."
                ),
                "correct_answer": "560",
                "hint": "Заявлено в названии квеста.",
                "point_rules": "Держитесь правой стороны при подъёме встречных групп.",
            },
            {
                "title": "Нижняя площадка",
                "latitude": 56.3315,
                "longitude": 44.0099,
                "task": (
                    "На постаменте катера-памятника написано его имя. "
                    "Введите это имя одним словом."
                ),
                "correct_answer": "герой",
                "hint": "Так называют отличившихся в бою.",
                "point_rules": "Не подходите близко к воде.",
            },
        ],
    },
    {
        "key": "rozhdestvenskaya",
        "title": "Рождественская: улица купцов",
        "description": (
            "Маршрут по главной торговой улице старого Нижнего: "
            "Строгановская церковь, доходные дома, Скоба и Речной вокзал."
        ),
        "location": "Нижний Новгород, Рождественская улица",
        "difficulty": 2,
        "duration_minutes": 55,
        "rules_and_warnings": "Прогулка проходит по проезжей улице — следите за транспортом.",
        # Архивирован создателем
        "status": QuestStatus.ARCHIVED,
        "creator_key": "polina",
        "points": [
            {
                "title": "Строгановская церковь",
                "latitude": 56.3279,
                "longitude": 44.0238,
                "task": (
                    "Церковь известна сложной резьбой. "
                    "Введите фамилию заказчика-купца (одна фамилия)."
                ),
                "correct_answer": "строганов",
                "hint": "Та же, что и в рецепте «бефстроганов».",
                "point_rules": "Не входите в храм во время богослужения.",
            },
            {
                "title": "Площадь Маркина (Скоба)",
                "latitude": 56.3292,
                "longitude": 44.0223,
                "task": (
                    "Старое название площади связано с её формой. "
                    "Введите одно слово — это название."
                ),
                "correct_answer": "скоба",
                "hint": "Изогнутая металлическая деталь.",
                "point_rules": None,
            },
            {
                "title": "Речной вокзал",
                "latitude": 56.3299,
                "longitude": 44.0064,
                "task": (
                    "С каким судном ассоциируется силуэт здания вокзала? "
                    "Введите одно слово."
                ),
                "correct_answer": "корабль",
                "hint": "Большое судно с палубой и трубой.",
                "point_rules": "Не выходите на грузовые пирсы.",
            },
        ],
    },
    {
        "key": "zarechnaya_temples",
        "title": "Древние храмы Заречья",
        "description": (
            "Тихий маршрут по нижегородскому Заречью: купеческие церкви, "
            "старые мостовые и Гордеевский холм с панорамным видом на Стрелку."
        ),
        "location": "Нижний Новгород, Канавинский и Московский районы",
        "difficulty": 3,
        "duration_minutes": 75,
        "rules_and_warnings": "Часть маршрута — частный сектор, говорите тихо.",
        "status": QuestStatus.PUBLISHED,
        "creator_key": "timofey",
        "points": [
            {
                "title": "Спасский собор",
                "latitude": 56.3249,
                "longitude": 43.9518,
                "task": (
                    "Собор венчает не привычное число куполов. "
                    "Введите количество цифрой."
                ),
                "correct_answer": "5",
                "hint": "Самое распространённое число для большого храма.",
                "point_rules": None,
            },
            {
                "title": "Смоленская церковь в Гордеевке",
                "latitude": 56.3234,
                "longitude": 43.9436,
                "task": (
                    "Введите имя купца, на чьи деньги построена церковь "
                    "(одна фамилия — та же, что и у церкви на Рождественской)."
                ),
                "correct_answer": "строганов",
                "hint": "Главные меценаты Нижнего конца XVII века.",
                "point_rules": None,
            },
            {
                "title": "Памятный знак переписчикам Дмитрия Минина",
                "latitude": 56.3261,
                "longitude": 43.9559,
                "task": (
                    "Введите век, к которому относится подвиг ополчения "
                    "(римскими цифрами)."
                ),
                "correct_answer": "xvii",
                "hint": "Семнадцатый.",
                "point_rules": None,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Прохождения квестов: соло (QuestRunModel) и командные (TeamQuestRunModel).
# Один пользователь может иметь только один in_progress run одновременно.
# Одна команда — только один активный team-run одновременно.
# ---------------------------------------------------------------------------

# Соло-прохождения (user_key, quest_key, status, started_offset_min, elapsed_min, points)
SOLO_RUNS: list[dict] = [
    # Алиса (соло-игрок) — активна и популярна
    {"user_key": "alisa", "quest_key": "kremlin_smolensk", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 6, "elapsed_minutes": 95, "points": 360},
    {"user_key": "alisa", "quest_key": "pokrovskaya_walk", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 4, "elapsed_minutes": 58, "points": 220},
    {"user_key": "alisa", "quest_key": "chkalov_stairs", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 2, "elapsed_minutes": 42, "points": 480},
    {"user_key": "alisa", "quest_key": "kremlin_nn", "status": QuestRunStatus.IN_PROGRESS,
     "started_minutes_ago": 35, "current_step_index": 2, "points": None},
    # Тимофей — несколько прохождений
    {"user_key": "timofey", "quest_key": "kremlin_smolensk", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 9, "elapsed_minutes": 110, "points": 280},
    {"user_key": "timofey", "quest_key": "pokrovskaya_walk", "status": QuestRunStatus.ABANDONED,
     "started_minutes_ago": 60 * 24 * 7, "elapsed_minutes": 25, "points": 0,
     "current_step_index": 1},
    # Никита — кросс-город прохождение
    {"user_key": "nikita", "quest_key": "strelka_volga", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 10, "elapsed_minutes": 78, "points": 380},
    {"user_key": "nikita", "quest_key": "blonye_secrets", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 5, "elapsed_minutes": 34, "points": 110},
    # Иван (NN) сходил в Смоленск
    {"user_key": "ivan", "quest_key": "ancient_heart", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 12, "elapsed_minutes": 130, "points": 290},
    # Анна забросила сложный
    {"user_key": "anna", "quest_key": "ancient_heart", "status": QuestRunStatus.ABANDONED,
     "started_minutes_ago": 60 * 24 * 8, "elapsed_minutes": 40, "points": 0,
     "current_step_index": 2},
    # Полина — два соло
    {"user_key": "polina", "quest_key": "kremlin_smolensk", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 11, "elapsed_minutes": 105, "points": 240},
    {"user_key": "polina", "quest_key": "literary_smolensk", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 3, "elapsed_minutes": 55, "points": 180},
    # Дмитрий — попробовал свой и чужой
    {"user_key": "dmitry", "quest_key": "literary_smolensk", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 6, "elapsed_minutes": 50, "points": 195},
    # Мария — короткий и удачный
    {"user_key": "maria", "quest_key": "blonye_secrets", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 4, "elapsed_minutes": 31, "points": 120},
    # Софья — сходила к стрелке
    {"user_key": "sofya", "quest_key": "strelka_volga", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 13, "elapsed_minutes": 82, "points": 360},
    # Артём — забросил
    {"user_key": "artem", "quest_key": "pokrovskaya_walk", "status": QuestRunStatus.ABANDONED,
     "started_minutes_ago": 60 * 24 * 14, "elapsed_minutes": 20, "points": 0,
     "current_step_index": 1},
    # Артём — успешный соло-прохождение
    {"user_key": "artem", "quest_key": "chkalov_stairs", "status": QuestRunStatus.COMPLETED,
     "started_minutes_ago": 60 * 24 * 2, "elapsed_minutes": 50, "points": 420},
]

# Командные прохождения. Создатель квеста не должен быть в команде.
TEAM_RUNS: list[dict] = [
    # «Стрелки Новгорода» (Иван — создатель Q6 и Q10) идут в Смоленск
    {
        "team_name": "Стрелки Новгорода",
        "quest_key": "kremlin_smolensk",  # автор Артём
        "status": TeamQuestRunStatus.COMPLETED,
        "started_minutes_ago": 60 * 24 * 5,
        "elapsed_minutes": 88,
        "points": 540,
        "completed_by_keys": ["ivan", "anna", "dmitry", "maria"],  # по чекпоинтам
    },
    {
        "team_name": "Стрелки Новгорода",
        "quest_key": "ancient_heart",  # автор Артём — ОК
        "status": TeamQuestRunStatus.COMPLETED,
        "started_minutes_ago": 60 * 24 * 2,
        "elapsed_minutes": 125,
        "points": 720,
        "completed_by_keys": ["ivan", "anna", "dmitry", "maria"],
    },
    # «Смоленские Соколы» (Артём, Софья, Никита) идут в Нижний
    {
        "team_name": "Смоленские Соколы",
        "quest_key": "strelka_volga",  # автор Иван — ОК
        "status": TeamQuestRunStatus.COMPLETED,
        "started_minutes_ago": 60 * 24 * 8,
        "elapsed_minutes": 75,
        "points": 580,
        "completed_by_keys": ["artem", "sofya", "nikita", "artem"],
    },
    {
        "team_name": "Смоленские Соколы",
        "quest_key": "kremlin_nn",  # автор Дмитрий — ОК
        "status": TeamQuestRunStatus.COMPLETED,
        "started_minutes_ago": 60 * 24 * 4,
        "elapsed_minutes": 92,
        "points": 610,
        "completed_by_keys": ["sofya", "artem", "nikita", "sofya", "artem"],
    },
    # «Поволжские Лисы» (Полина, Тимофей)
    {
        "team_name": "Поволжские Лисы",
        "quest_key": "literary_smolensk",  # автор Софья — ОК
        "status": TeamQuestRunStatus.COMPLETED,
        "started_minutes_ago": 60 * 24 * 6,
        "elapsed_minutes": 53,
        "points": 320,
        "completed_by_keys": ["polina", "timofey", "polina"],
    },
    {
        "team_name": "Поволжские Лисы",
        "quest_key": "chkalov_stairs",  # автор Иван — ОК
        "status": TeamQuestRunStatus.IN_PROGRESS,
        "started_minutes_ago": 18,
        "elapsed_minutes": None,
        "points": None,
        "completed_by_keys": ["polina"],  # один чекпоинт уже пройден
    },
]


# ---------------------------------------------------------------------------
# Жалобы (для модерации)
# ---------------------------------------------------------------------------

COMPLAINTS: list[dict] = [
    {
        "quest_key": "dnieper_sunset",
        "author_key": "alisa",
        "reason": (
            "В описании квеста есть пункт о вечерней прогулке — для подростков "
            "14–15 лет это может быть небезопасно, особенно у воды."
        ),
    },
    {
        "quest_key": "pokrovskaya_walk",
        "author_key": "polina",
        "reason": (
            "На точке у Памятника Козе ответ-подсказка слишком очевиден, прошу "
            "пересмотреть формулировку задания."
        ),
    },
]


# ---------------------------------------------------------------------------
# Избранное
# ---------------------------------------------------------------------------

FAVORITES: list[tuple[str, str]] = [
    ("alisa", "kremlin_nn"),
    ("alisa", "strelka_volga"),
    ("timofey", "kremlin_smolensk"),
    ("polina", "blonye_secrets"),
    ("nikita", "chkalov_stairs"),
    ("anna", "kremlin_smolensk"),
    ("maria", "literary_smolensk"),
]


# ---------------------------------------------------------------------------
# Логика наполнения
# ---------------------------------------------------------------------------

DEMO_USER_EMAILS = [u["email"] for u in USERS]
DEMO_QUEST_TITLES = [q["title"] for q in QUESTS]
DEMO_TEAM_NAMES = [t["name"] for t in TEAMS]


async def wipe_demo_data(session) -> None:
    """Удаляет именно демо-набор (по email/тайтлам), не трогая чужие данные."""
    user_ids_q = await session.execute(select(UserModel.id).where(UserModel.email.in_(DEMO_USER_EMAILS)))
    user_ids = list(user_ids_q.scalars().all())
    quest_ids_q = await session.execute(select(QuestModel.id).where(QuestModel.title.in_(DEMO_QUEST_TITLES)))
    quest_ids = list(quest_ids_q.scalars().all())
    team_ids_q = await session.execute(select(TeamModel.id).where(TeamModel.name.in_(DEMO_TEAM_NAMES)))
    team_ids = list(team_ids_q.scalars().all())

    if quest_ids:
        await session.execute(delete(TeamQuestRunCheckpointModel).where(
            TeamQuestRunCheckpointModel.run_id.in_(
                select(TeamQuestRunModel.id).where(TeamQuestRunModel.quest_id.in_(quest_ids))
            )
        ))
        await session.execute(delete(TeamQuestRunParticipantModel).where(
            TeamQuestRunParticipantModel.run_id.in_(
                select(TeamQuestRunModel.id).where(TeamQuestRunModel.quest_id.in_(quest_ids))
            )
        ))
        await session.execute(delete(TeamQuestRunModel).where(TeamQuestRunModel.quest_id.in_(quest_ids)))
        await session.execute(delete(QuestRunModel).where(QuestRunModel.quest_id.in_(quest_ids)))
        await session.execute(delete(QuestComplaintModel).where(QuestComplaintModel.quest_id.in_(quest_ids)))
        await session.execute(delete(QuestFavoriteModel).where(QuestFavoriteModel.quest_id.in_(quest_ids)))
        await session.execute(delete(QuestPointModel).where(QuestPointModel.quest_id.in_(quest_ids)))
        await session.execute(delete(QuestModel).where(QuestModel.id.in_(quest_ids)))

    if team_ids:
        await session.execute(delete(TeamQuestRunModel).where(TeamQuestRunModel.team_id.in_(team_ids)))

    if user_ids:
        await session.execute(delete(QuestRunModel).where(QuestRunModel.user_id.in_(user_ids)))
        await session.execute(delete(UserAchievementModel).where(UserAchievementModel.user_id.in_(user_ids)))
        # Отвязываем пользователей от команд, чтобы можно было удалить команды
        await session.execute(
            UserModel.__table__.update().where(UserModel.id.in_(user_ids)).values(team_id=None)
        )

    if team_ids:
        await session.execute(delete(TeamModel).where(TeamModel.id.in_(team_ids)))

    if user_ids:
        await session.execute(delete(UserModel).where(UserModel.id.in_(user_ids)))

    await session.commit()


async def ensure_default_achievements(session) -> None:
    existing_q = await session.execute(select(AchievementModel))
    existing = list(existing_q.scalars().all())
    if existing:
        return
    for payload in load_default_achievements():
        session.add(AchievementModel(image_file_id=None, **payload))
    await session.commit()


def naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


async def seed_users(session) -> dict[str, UserModel]:
    users: dict[str, UserModel] = {}
    for u in USERS:
        model = UserModel(
            username=u["username"],
            email=u["email"],
            hashed_password=hash_password(u["password"]),
            birthdate=u["birthdate"],
            role=u["role"],
            total_points=0,
            created_at=naive_now(),
        )
        session.add(model)
        users[u["key"]] = model
    await session.flush()
    return users


async def seed_teams(session, users: dict[str, UserModel]) -> dict[str, TeamModel]:
    teams: dict[str, TeamModel] = {}
    for t in TEAMS:
        team = TeamModel(
            name=t["name"],
            description=t["description"],
            code=t["code"],
            creator_id=users[t["creator_key"]].id,
            created_at=naive_now(),
        )
        session.add(team)
        await session.flush()
        for member_key in t["member_keys"]:
            users[member_key].team_id = team.id
        teams[t["name"]] = team
    await session.flush()
    return teams


async def seed_quests(session, users: dict[str, UserModel]) -> dict[str, QuestModel]:
    quests: dict[str, QuestModel] = {}
    for q in QUESTS:
        quest = QuestModel(
            title=q["title"],
            description=q["description"],
            location=q["location"],
            difficulty=q["difficulty"],
            duration_minutes=q["duration_minutes"],
            rules_and_warnings=q.get("rules_and_warnings"),
            image_file_id=None,
            rejection_reason=q.get("rejection_reason"),
            status=q["status"],
            creator_id=users[q["creator_key"]].id,
            created_at=naive_now(),
        )
        for p in q["points"]:
            quest.points.append(
                QuestPointModel(
                    title=p["title"],
                    latitude=p["latitude"],
                    longitude=p["longitude"],
                    task=p["task"],
                    correct_answer=p["correct_answer"],
                    hint=p.get("hint"),
                    point_rules=p.get("point_rules"),
                    created_at=naive_now(),
                )
            )
        session.add(quest)
        quests[q["key"]] = quest
    await session.flush()
    return quests


async def seed_solo_runs(
    session,
    users: dict[str, UserModel],
    quests: dict[str, QuestModel],
) -> None:
    for run in SOLO_RUNS:
        user = users[run["user_key"]]
        quest = quests[run["quest_key"]]
        started_at = NOW - timedelta(minutes=run["started_minutes_ago"])
        completed_at: datetime | None = None
        current_step_index: int

        if run["status"] == QuestRunStatus.COMPLETED:
            completed_at = started_at + timedelta(minutes=run["elapsed_minutes"])
            current_step_index = len(quest.points)
        elif run["status"] == QuestRunStatus.ABANDONED:
            completed_at = started_at + timedelta(minutes=run["elapsed_minutes"])
            current_step_index = run.get("current_step_index", 0)
        else:  # IN_PROGRESS
            current_step_index = run.get("current_step_index", 0)

        points = run.get("points")
        session.add(
            QuestRunModel(
                user_id=user.id,
                quest_id=quest.id,
                status=run["status"],
                started_at=started_at,
                completed_at=completed_at,
                current_step_index=current_step_index,
                points_awarded=points,
                created_at=naive_now(),
            )
        )
        if points:
            user.total_points += points


async def seed_team_runs(
    session,
    users: dict[str, UserModel],
    teams: dict[str, TeamModel],
    quests: dict[str, QuestModel],
) -> None:
    for run_data in TEAM_RUNS:
        team = teams[run_data["team_name"]]
        quest = quests[run_data["quest_key"]]
        started_at = NOW - timedelta(minutes=run_data["started_minutes_ago"])
        completed_at: datetime | None = None
        if run_data["status"] == TeamQuestRunStatus.COMPLETED:
            completed_at = started_at + timedelta(minutes=run_data["elapsed_minutes"])

        team_run = TeamQuestRunModel(
            team_id=team.id,
            quest_id=quest.id,
            status=run_data["status"],
            starts_at=started_at,
            started_at=started_at,
            completed_at=completed_at,
            points_awarded=run_data.get("points"),
            created_at=naive_now(),
        )
        # Участники — все актуальные члены команды на момент прохождения
        member_users = [u for u in users.values() if u.team_id == team.id]
        for m in member_users:
            team_run.participants.append(
                TeamQuestRunParticipantModel(
                    user_id=m.id,
                    ready_at=started_at - timedelta(seconds=30),
                    created_at=naive_now(),
                )
            )

        # Чекпоинты, выполненные в порядке
        sorted_points = sorted(quest.points, key=lambda p: p.id)
        completed_keys = run_data.get("completed_by_keys", [])
        elapsed_total = run_data.get("elapsed_minutes")
        completed_count = (
            len(sorted_points) if run_data["status"] == TeamQuestRunStatus.COMPLETED
            else len(completed_keys)
        )
        for idx in range(completed_count):
            point = sorted_points[idx]
            user_key = completed_keys[idx] if idx < len(completed_keys) else completed_keys[-1]
            user = users[user_key]
            if elapsed_total:
                fraction = (idx + 1) / len(sorted_points)
                cp_completed_at = started_at + timedelta(
                    minutes=elapsed_total * fraction
                )
            else:
                cp_completed_at = NOW - timedelta(minutes=2)
            team_run.checkpoints.append(
                TeamQuestRunCheckpointModel(
                    quest_point_id=point.id,
                    completed_by_user_id=user.id,
                    completed_at=cp_completed_at,
                    created_at=naive_now(),
                )
            )

        session.add(team_run)

        # Распределяем командные очки поровну между участниками
        points = run_data.get("points")
        if points and member_users:
            per_member = points // len(member_users)
            remainder = points - per_member * len(member_users)
            for i, m in enumerate(member_users):
                m.total_points += per_member + (1 if i < remainder else 0)


async def seed_complaints(
    session,
    users: dict[str, UserModel],
    quests: dict[str, QuestModel],
) -> None:
    for c in COMPLAINTS:
        session.add(
            QuestComplaintModel(
                reason=c["reason"],
                quest_id=quests[c["quest_key"]].id,
                author_id=users[c["author_key"]].id,
                created_at=naive_now(),
            )
        )


async def seed_favorites(
    session,
    users: dict[str, UserModel],
    quests: dict[str, QuestModel],
) -> None:
    for user_key, quest_key in FAVORITES:
        session.add(
            QuestFavoriteModel(
                user_id=users[user_key].id,
                quest_id=quests[quest_key].id,
                created_at=naive_now(),
            )
        )


async def award_user_achievements(session, users: dict[str, UserModel]) -> None:
    """Простая раздача достижений по уже посчитанным total_points.

    Без обращения к рейтинговым достижениям (rating_first_place и т.п.) — их
    выдаст AchievementService на лету при первом запросе профиля.
    """
    achievements_q = await session.execute(
        select(AchievementModel).where(AchievementModel.criteria == AchievementCriteria.POINTS)
    )
    point_achievements = sorted(
        achievements_q.scalars().all(),
        key=lambda a: a.points_required or 0,
    )
    awarded_at = NOW - timedelta(hours=1)
    for user in users.values():
        if user.role != UserRole.USER:
            continue
        for ach in point_achievements:
            if ach.points_required is None:
                continue
            if user.total_points >= ach.points_required:
                session.add(
                    UserAchievementModel(
                        user_id=user.id,
                        achievement_id=ach.id,
                        awarded_at=awarded_at,
                        created_at=naive_now(),
                    )
                )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("Подключаемся к %s ...", settings.postgres_url)
    engine = create_async_engine(settings.postgres_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as session:
        logger.info("Очищаем демо-данные (если уже были)...")
        await wipe_demo_data(session)

        logger.info("Создаём дефолтные достижения...")
        await ensure_default_achievements(session)

        logger.info("Создаём пользователей...")
        users = await seed_users(session)

        logger.info("Создаём команды...")
        teams = await seed_teams(session, users)

        logger.info("Создаём квесты и чекпоинты...")
        quests = await seed_quests(session, users)
        await session.commit()

        logger.info("Создаём соло-прохождения...")
        await seed_solo_runs(session, users, quests)

        logger.info("Создаём командные прохождения...")
        await seed_team_runs(session, users, teams, quests)

        logger.info("Создаём жалобы и избранное...")
        await seed_complaints(session, users, quests)
        await seed_favorites(session, users, quests)
        await session.commit()

        logger.info("Раздаём достижения по очкам...")
        await award_user_achievements(session, users)
        await session.commit()

    await engine.dispose()

    print()
    print("=" * 70)
    print(" Демо-данные загружены ✓")
    print("=" * 70)
    print(f" Модератор:  email=moderator@strelka.ru   password={DEMO_PASSWORD}")
    print(f" Игроки:     email=<имя>@example.com      password={DEMO_PASSWORD}")
    print(" (бриф просил «demo123» — но валидация LoginRequest требует ≥8 символов)")
    print()
    print(" Учётные записи:")
    for u in USERS:
        print(f"   - {u['username']:<18}  {u['email']}")
    print()
    print(" Города: Смоленск (6 квестов), Нижний Новгород (6 квестов)")
    print(f" Команды: {', '.join(t['name'] for t in TEAMS)}")
    print(f" Прохождений: {len(SOLO_RUNS)} соло + {len(TEAM_RUNS)} командных")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
