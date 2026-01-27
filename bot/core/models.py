from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set


@dataclass
class PetState:
    name: str
    avatar_key: str = "awake"  # ключ для выбора изображения выдры
    happiness: int = 50        # 0–100
    energy: int = 50           # 0–100
    hunger: int = 50           # 0–100 (чем выше, тем сытее)
    thirst: int = 50           # 0–100 (чем выше, тем напоеннее)
    age_days: int = 0
    is_alive: bool = True
    free_revives_left: int = 1
    last_sleep_start: Optional[str] = None  # ISO-строка
    last_wake_time: Optional[str] = None
    unlocked_hobbies: List[str] = field(default_factory=list)
    hobby_sessions: Optional['HobbySession'] = None  # текущая активная сессия
    hobby_mastery: Dict[str, 'HobbyMastery'] = field(default_factory=dict)  # hobby_id -> HobbyMastery
    money: int = 0
    at_work: bool = False
    last_work_start: Optional[str] = None   # ISO-строка
    last_interaction: Optional[str] = None  # ISO-строка последнего действия
    fatigue: int = 0  # 0-100, усталость от работы
    unlocked_achievements: List[str] = field(default_factory=list)  # ID разблокированных достижений
    critical_state_since: Optional[str] = None  # ISO-строка, когда выдра в критическом состоянии
    vacation_mode: bool = False  # Режим отпуска (для редких пользователей)


@dataclass
class UserSettings:
    timezone: str
    pet_name: Optional[str] = None
    water_norm_liters: float = 2.5  # норма воды в день (литры)
    glass_volume_ml: int = 300  # объем стакана в миллилитрах
    water_norm_set: bool = False  # была ли установлена норма воды


@dataclass
class DailyStats:
    """Статистика за один день"""
    date: str  # ISO дата
    sleep_minutes: int = 0  # общее время сна в минутах (пользователь)
    water_liters: float = 0.0  # выпито воды в литрах (пользователь)
    wake_time: Optional[str] = None  # время пробуждения ISO
    sleep_time: Optional[str] = None  # время засыпания ISO
    pet_sleep_minutes: int = 0  # сколько спала выдра (в минутах)
    pet_water_glasses: int = 0  # сколько стаканов воды выпила выдра


@dataclass
class AdviceState:
    """Состояние системы советов для пользователя"""
    last_advice_date: Optional[str] = None  # дата последнего полученного совета
    shown_advice_ids: List[str] = field(default_factory=list)  # ID показанных советов за неделю
    week_start_date: Optional[str] = None  # дата начала текущей недели
    monthly_advice_summary: Dict[str, List[str]] = field(default_factory=dict)  # категория -> список советов за месяц
    first_advice_date: Optional[str] = None  # дата первого полученного совета (для расчета месячного отчета)
    weekly_answers: Dict[str, bool] = field(default_factory=dict)  # дата недели -> соблюдал ли советы (True/False)


@dataclass
class UserState:
    user_id: int
    pet: PetState
    settings: UserSettings
    last_reminders: Dict[str, str] = field(default_factory=dict)  # тип -> дата ISO
    work_hours_by_date: Dict[str, float] = field(default_factory=dict)  # дата ISO -> отработанные часы
    daily_stats: Dict[str, DailyStats] = field(default_factory=dict)  # дата ISO -> статистика дня
    advice_state: AdviceState = field(default_factory=AdviceState)
    last_main_menu_return: Optional[str] = None  # время последнего возврата в главное меню
    active_quests: Dict[str, Dict] = field(default_factory=dict)  # ID квеста -> данные квеста
    work_stats: Dict[str, any] = field(default_factory=dict)  # Статистика работы
    last_fatigue_update: Optional[str] = None  # ISO дата последнего обновления усталости


@dataclass
class AdminSettings:
    admin_ids: List[int] = field(default_factory=list)
    required_channel_username: Optional[str] = None


@dataclass
class Hobby:
    id: str
    title: str
    price: int  # цена в монетах
    avatar_key: str  # ключ состояния выдры для этого хобби
    hobby_type: str = "sport"  # sport, creative, entertainment
    base_happiness: int = 10  # базовое увеличение счастья (зависит от цены)
    base_fatigue_recovery: int = 100  # базовое восстановление от усталости
    duration_minutes: int = 60  # длительность сессии в минутах


@dataclass
class HobbySession:
    """Активная сессия хобби"""
    hobby_id: str
    start_time: str  # ISO время начала
    duration_minutes: int


@dataclass
class HobbyMastery:
    """Уровень мастерства в хобби"""
    hobby_id: str
    level: int = 1  # 1-5 звёзд
    total_sessions: int = 0  # всего сессий
    streak: int = 0  # текущий стрик (дни подряд)
    last_session_date: Optional[str] = None  # дата последней сессии (для стрика)


def hobby_to_dict(hobby: Hobby) -> Dict:
    return asdict(hobby)


def pet_to_dict(pet: PetState) -> Dict:
    return asdict(pet)


def daily_stats_to_dict(stats: DailyStats) -> Dict:
    return asdict(stats)


def advice_state_to_dict(advice: AdviceState) -> Dict:
    return asdict(advice)


def user_to_dict(user: UserState) -> Dict:
    return {
        "user_id": user.user_id,
        "pet": pet_to_dict(user.pet),
        "settings": {
            "timezone": user.settings.timezone,
            "pet_name": user.settings.pet_name,
            "water_norm_liters": user.settings.water_norm_liters,
            "glass_volume_ml": user.settings.glass_volume_ml,
            "water_norm_set": user.settings.water_norm_set,
        },
        "last_reminders": user.last_reminders,
        "work_hours_by_date": user.work_hours_by_date,
        "daily_stats": {
            date: daily_stats_to_dict(stats) for date, stats in user.daily_stats.items()
        },
        "advice_state": advice_state_to_dict(user.advice_state),
        "last_main_menu_return": user.last_main_menu_return,
        "active_quests": user.active_quests,
        "work_stats": user.work_stats,
        "last_fatigue_update": user.last_fatigue_update,
    }


def admin_to_dict(admin: AdminSettings) -> Dict:
    return asdict(admin)


@dataclass
class Friendship:
    """Дружба между двумя пользователями"""
    user_id_1: int
    user_id_2: int
    friendship_level: int = 1  # 1–10 звёзд
    total_sessions_together: int = 0  # всего совместных активностей
    first_met_date: str = ""  # ISO дата
    last_interaction: str = ""  # ISO дата
    social_bonuses: Dict[str, int] = field(default_factory=dict)
    # bonuses: {"happiness": 10, "money": 5, "experience": 3}


@dataclass
class SocialAchievement:
    """Совместное достижение (для двух и более выдр)"""
    id: str
    title: str
    description: str
    icon: str
    requirement: str  # e.g., "10_sessions_together", "100_friendship_level"
    reward_coins: int = 0
    reward_happiness: int = 0
    reward_experience: int = 0


@dataclass
class CoopSession:
    """Сессия совместной активности"""
    id: str
    activity_type: str  # "work", "hobby", "walk", "training", "challenge", etc.
    user_ids: List[int]
    start_time: str
    duration_minutes: int
    result_happiness: Dict[int, int] = field(default_factory=dict)  # user_id -> happiness gained
    result_money: Dict[int, int] = field(default_factory=dict)
    event_triggered: Optional[str] = None  # описание события

