"""
Система дружбы и совместных активностей
"""
import random
from datetime import datetime, timezone
from typing import Tuple, Dict, List, Optional

from bot.core.models import Friendship, SocialAchievement, CoopSession


# События при совместных активностях
COOP_EVENTS = {
    "work": [
        ("positive", "🤝", "Вы отлично работали вместе! +20 счастья каждому", 20),
        ("positive", "🚀", "Супер-синергия! Заработок +30%", 0),  # Специальный эффект
        ("positive", "⭐", "Напарники высокого уровня! +25 счастья", 25),
        ("positive", "💪", "Вместе мы сильнее! +150 монет бонус за командную работу", 0),
        ("neutral", "😊", "Нормальный рабочий день, +10 счастья", 10),
        ("negative", "😅", "Немного разногласий, но работа сделана, +5 счастья", 5),
        ("negative", "🤨", "Было сложновато работать, -5 счастья", -5),
    ],
    "hobby": [
        ("positive", "🎨", "Создали шедевр вместе! +30 счастья каждому", 30),
        ("positive", "✨", "Вдохновение заразительно! +250 восстановления", 0),
        ("positive", "🌟", "Вы идеально дополняете друг друга! +25 счастья", 25),
        ("positive", "👏", "Аплодисменты зрителей! +20 счастья", 20),
        ("neutral", "😊", "Приятно провели время, +10 счастья", 10),
        ("negative", "😕", "Не совсем срослось, но было весело, +5 счастья", 5),
    ],
    "walk": [
        ("positive", "🌳", "Прекрасная прогулка вместе! +15 счастья", 15),
        ("positive", "🦌", "Встретили оленя! Какой день! +20 счастья", 20),
        ("positive", "🏞️", "Нашли волшебное место! +25 счастья", 25),
        ("neutral", "😊", "Хорошая прогулка, +10 счастья", 10),
        ("negative", "🌧️", "Дождь испортил прогулку, но компания спасла день, +8 счастья", 8),
    ],
    "training": [
        ("positive", "💪", "Отличная тренировка! +30 счастья, +200 восстановления", 30),
        ("positive", "🏆", "Мотивировали друг друга! +300 восстановления", 0),
        ("positive", "🥇", "Оба в отличной форме! +25 счастья", 25),
        ("neutral", "😓", "Изнурительно, но вместе легче, +10 счастья", 10),
        ("negative", "😫", "Было сложно, но поддержка помогла, +5 счастья", 5),
    ],
    "meal": [
        ("positive", "🍽️", "Чудесный обед вместе! +25 счастья каждому", 25),
        ("positive", "😋", "Вкусная еда и весёлые разговоры! +30 счастья", 30),
        ("positive", "🥂", "Отмечали друг друга! +35 счастья", 35),
        ("neutral", "😊", "Приятный обед, +15 счастья", 15),
        ("negative", "😐", "Обычный обед, +8 счастья", 8),
    ],
}

# Совместные достижения (20+ штук)
SOCIAL_ACHIEVEMENTS = [
    SocialAchievement(
        id="first_friend",
        title="Нашёл друга! 👥",
        description="Добавил первого друга",
        icon="👥",
        requirement="first_friend",
        reward_happiness=20,
        reward_coins=50,
    ),
    SocialAchievement(
        id="best_friends",
        title="Лучшие друзья ⭐⭐⭐⭐⭐",
        description="Дружба уровня 5 со своим другом",
        icon="⭐⭐⭐⭐⭐",
        requirement="friendship_level_5",
        reward_happiness=100,
        reward_coins=500,
    ),
    SocialAchievement(
        id="brothers",
        title="Братья/сёстры ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐",
        description="Дружба уровня 10 (максимум) со своим другом",
        icon="🫂",
        requirement="friendship_level_10",
        reward_happiness=200,
        reward_coins=1000,
        reward_experience=100,
    ),
    SocialAchievement(
        id="10_sessions_together",
        title="Опытные товарищи",
        description="10 совместных активностей с одним другом",
        icon="🤝",
        requirement="10_sessions_together",
        reward_happiness=50,
        reward_coins=200,
    ),
    SocialAchievement(
        id="popular_otter",
        title="Любимая выдра! 💫",
        description="3 друга с дружбой уровня 3+",
        icon="💫",
        requirement="3_friends_level_3",
        reward_happiness=75,
        reward_coins=300,
    ),
    SocialAchievement(
        id="social_butterfly",
        title="Социальная бабочка 🦋",
        description="5 друзей одновременно",
        icon="🦋",
        requirement="5_friends",
        reward_happiness=150,
        reward_coins=500,
    ),
    SocialAchievement(
        id="50_coop_sessions",
        title="Командный игрок",
        description="50 совместных активностей (с кем угодно)",
        icon="🏃",
        requirement="50_coop_sessions",
        reward_happiness=100,
        reward_coins=750,
        reward_experience=50,
    ),
    SocialAchievement(
        id="friend_helper",
        title="Добрый самаритянин 💝",
        description="Помог другу завершить сложную активность",
        icon="💝",
        requirement="helped_friend",
        reward_happiness=30,
        reward_coins=100,
    ),
    SocialAchievement(
        id="coop_victory",
        title="Совместная победа 🏆",
        description="Выиграли спортивный вызов с другом",
        icon="🏆",
        requirement="coop_challenge_victory",
        reward_happiness=75,
        reward_coins=250,
    ),
    SocialAchievement(
        id="first_group_hobby",
        title="Творческий дуэт 🎨",
        description="Первое совместное хобби с друзьями",
        icon="🎨",
        requirement="first_coop_hobby",
        reward_happiness=40,
        reward_coins=150,
    ),
]


def get_friendship_level(sessions: int) -> int:
    """Рассчитывает уровень дружбы на основе совместных сессий"""
    if sessions < 3:
        return 1
    elif sessions < 7:
        return 2
    elif sessions < 15:
        return 3
    elif sessions < 30:
        return 4
    elif sessions < 50:
        return 5
    elif sessions < 75:
        return 6
    elif sessions < 100:
        return 7
    elif sessions < 150:
        return 8
    elif sessions < 200:
        return 9
    else:
        return 10


def get_friendship_bonuses(level: int) -> Dict[str, float]:
    """Получить бонусы за уровень дружбы"""
    bonuses = {
        1: {"happiness": 1.0, "money": 1.0, "experience": 1.0},
        2: {"happiness": 1.1, "money": 1.05, "experience": 1.05},
        3: {"happiness": 1.15, "money": 1.1, "experience": 1.1},
        4: {"happiness": 1.2, "money": 1.15, "experience": 1.15},
        5: {"happiness": 1.25, "money": 1.2, "experience": 1.2},
        6: {"happiness": 1.3, "money": 1.25, "experience": 1.25},
        7: {"happiness": 1.35, "money": 1.3, "experience": 1.3},
        8: {"happiness": 1.4, "money": 1.35, "experience": 1.35},
        9: {"happiness": 1.45, "money": 1.4, "experience": 1.4},
        10: {"happiness": 1.5, "money": 1.45, "experience": 1.45},
    }
    return bonuses.get(level, bonuses[1])


def get_num_participants_bonus(num_participants: int) -> float:
    """Бонус за количество участников совместной активности"""
    bonuses = {
        2: 1.2,
        3: 1.35,
        4: 1.5,
        5: 1.65,
        6: 1.8,
    }
    return bonuses.get(min(num_participants, 6), 1.0)


def get_friendship_stars(level: int) -> str:
    """Возвращает звёзды дружбы"""
    return "⭐" * level + "☆" * (10 - level)


def get_random_coop_event(activity_type: str) -> Tuple[str, str, str, int]:
    """Получить случайное событие для совместной активности"""
    events = COOP_EVENTS.get(activity_type, COOP_EVENTS.get("walk"))
    event_type, emoji, text, modifier = random.choice(events)
    return event_type, emoji, text, modifier


def format_friendship_info(user1_id: int, user2_id: int, friendship: Friendship) -> str:
    """Форматирует информацию о дружбе"""
    level = friendship.friendship_level
    sessions = friendship.total_sessions_together
    stars = get_friendship_stars(level)
    bonuses = get_friendship_bonuses(level)
    
    message = (
        f"👥 Дружба между выдрами\n\n"
        f"⭐ Уровень: {stars} ({level}/10)\n"
        f"👥 Совместных активностей: {sessions}\n"
        f"📅 Дружат с: {friendship.first_met_date}\n"
        f"🕐 Последнее взаимодействие: {friendship.last_interaction}\n\n"
        f"💰 Бонусы:\n"
        f"😊 Счастье: +{int((bonuses['happiness'] - 1) * 100)}%\n"
        f"💵 Деньги: +{int((bonuses['money'] - 1) * 100)}%\n"
        f"📈 Опыт: +{int((bonuses['experience'] - 1) * 100)}%\n"
    )
    
    return message


def format_coop_result(
    activity_type: str,
    participants: int,
    happiness_gained: int,
    money_gained: int,
    event_emoji: str,
    event_text: str,
    friendships_updated: int,
) -> str:
    """Форматирует результат совместной активности"""
    activity_names = {
        "work": "💼 Совместная работа",
        "hobby": "🎨 Совместное хобби",
        "walk": "🚶 Совместная прогулка",
        "training": "💪 Совместная тренировка",
        "meal": "🍽️ Совместный обед",
    }
    
    activity_name = activity_names.get(activity_type, "Совместная активность")
    
    message = (
        f"{activity_name}\n\n"
        f"👥 Участников: {participants} выдр(ы)\n"
        f"{event_emoji} {event_text}\n\n"
        f"📊 Результаты для каждой выдры:\n"
        f"😊 Счастье: +{happiness_gained}\n"
        f"💵 Деньги: +{money_gained}\n\n"
        f"💕 Дружба укрепилась у {friendships_updated} пар!\n"
    )
    
    return message


def get_social_achievement_by_id(achievement_id: str) -> Optional[SocialAchievement]:
    """Получить достижение по ID"""
    for achievement in SOCIAL_ACHIEVEMENTS:
        if achievement.id == achievement_id:
            return achievement
    return None


def list_all_social_achievements() -> List[SocialAchievement]:
    """Получить список всех совместных достижений"""
    return SOCIAL_ACHIEVEMENTS
