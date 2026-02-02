from typing import Dict, Optional, List

from bot.core.models import (
    AdminSettings,
    PetState,
    UserSettings,
    UserState,
    Hobby,
    DailyStats,
    AdviceState,
    Friendship,
    CoopSession,
    admin_to_dict,
    user_to_dict,
    hobby_to_dict,
)
from bot.storage.json_db import JsonDB


class UsersRepository:
    def __init__(self) -> None:
        self._db = JsonDB("users.json")

    def get_user(self, user_id: int) -> Optional[UserState]:
        data = self._db.get(str(user_id))
        if not data:
            return None

        pet_data = data["pet"]
        pet = PetState(**pet_data)
        settings_data = data.get("settings", {})
        settings = UserSettings(
            timezone=settings_data.get("timezone", "Asia/Vladivostok"),
            pet_name=settings_data.get("pet_name"),
            water_norm_liters=settings_data.get("water_norm_liters", 2.5),
            glass_volume_ml=settings_data.get("glass_volume_ml", 300),
            water_norm_set=settings_data.get("water_norm_set", False),
            sleep_norm_hours=settings_data.get("sleep_norm_hours", 0.0),
        )
        
        # Восстанавливаем статистику дней
        daily_stats_raw = data.get("daily_stats", {})
        daily_stats = {}
        for date, stats_data in daily_stats_raw.items():
            daily_stats[date] = DailyStats(**stats_data)
        
        # Восстанавливаем состояние советов
        advice_data = data.get("advice_state", {})
        advice_state = AdviceState(**advice_data) if advice_data else AdviceState()
        
        # Восстанавливаем friendships
        friendships_raw = data.get("friendships", {})
        friendships = {}
        for friend_id_str, friendship_data in friendships_raw.items():
            try:
                friend_id = int(friend_id_str)
                friendships[friend_id] = Friendship(**friendship_data)
            except (ValueError, TypeError, KeyError):
                continue  # Пропускаем некорректные данные
        
        return UserState(
            user_id=data["user_id"],
            pet=pet,
            settings=settings,
            last_reminders=data.get("last_reminders", {}),
            work_hours_by_date=data.get("work_hours_by_date", {}),
            daily_stats=daily_stats,
            advice_state=advice_state,
            last_main_menu_return=data.get("last_main_menu_return"),
            active_quests=data.get("active_quests", {}),
            work_stats=data.get("work_stats", {}),
            last_fatigue_update=data.get("last_fatigue_update"),
            friendships=friendships,
        )

    def save_user(self, user: UserState) -> None:
        self._db.set(str(user.user_id), user_to_dict(user))

    def get_all_users(self) -> Dict[str, UserState]:
        raw = self._db.get_all()
        result: Dict[str, UserState] = {}
        for uid, data in raw.items():
            pet_data = data["pet"]
            # Обрабатываем старые данные без новых полей
            pet = PetState(
                name=pet_data["name"],
                avatar_key=pet_data.get("avatar_key", "awake"),
                happiness=pet_data.get("happiness", 50),
                energy=pet_data.get("energy", 50),
                hunger=pet_data.get("hunger", 50),
                thirst=pet_data.get("thirst", 50),
                age_days=pet_data.get("age_days", 0),
                is_alive=pet_data.get("is_alive", True),
                free_revives_left=pet_data.get("free_revives_left", 1),
                last_sleep_start=pet_data.get("last_sleep_start"),
                last_wake_time=pet_data.get("last_wake_time"),
                unlocked_hobbies=pet_data.get("unlocked_hobbies", []),
                money=pet_data.get("money", 0),
                at_work=pet_data.get("at_work", False),
                last_work_start=pet_data.get("last_work_start"),
                last_interaction=pet_data.get("last_interaction"),
                fatigue=pet_data.get("fatigue", 0),
                unlocked_achievements=pet_data.get("unlocked_achievements", []),
                critical_state_since=pet_data.get("critical_state_since"),
                vacation_mode=pet_data.get("vacation_mode", False),
            )
            settings_data = data.get("settings", {})
            settings = UserSettings(
                timezone=settings_data.get("timezone", "Asia/Vladivostok"),
                pet_name=settings_data.get("pet_name"),
                water_norm_liters=settings_data.get("water_norm_liters", 2.5),
                glass_volume_ml=settings_data.get("glass_volume_ml", 300),
                water_norm_set=settings_data.get("water_norm_set", False),
            )
            # Восстанавливаем статистику дней
            daily_stats_raw = data.get("daily_stats", {})
            daily_stats = {}
            for date, stats_data in daily_stats_raw.items():
                daily_stats[date] = DailyStats(**stats_data)
            
            # Восстанавливаем состояние советов
            advice_data = data.get("advice_state", {})
            if advice_data is not None and advice_data:
                # Обрабатываем старые данные без новых полей
                advice_state = AdviceState(
                    last_advice_date=advice_data.get("last_advice_date"),
                    shown_advice_ids=advice_data.get("shown_advice_ids", []),
                    week_start_date=advice_data.get("week_start_date"),
                    monthly_advice_summary=advice_data.get("monthly_advice_summary", {}),
                    first_advice_date=advice_data.get("first_advice_date"),
                    weekly_answers=advice_data.get("weekly_answers", {}),
                )
            else:
                advice_state = AdviceState()
            
            # Восстанавливаем friendships
            friendships_raw = data.get("friendships", {})
            friendships = {}
            for friend_id_str, friendship_data in friendships_raw.items():
                try:
                    friend_id = int(friend_id_str)
                    friendships[friend_id] = Friendship(**friendship_data)
                except (ValueError, TypeError, KeyError):
                    continue  # Пропускаем некорректные данные
            
            result[uid] = UserState(
                user_id=data["user_id"],
                pet=pet,
                settings=settings,
                last_reminders=data.get("last_reminders", {}),
                work_hours_by_date=data.get("work_hours_by_date", {}),
                daily_stats=daily_stats,
                advice_state=advice_state,
                last_main_menu_return=data.get("last_main_menu_return"),
                active_quests=data.get("active_quests", {}),
                work_stats=data.get("work_stats", {}),
                last_fatigue_update=data.get("last_fatigue_update"),
                friendships=friendships,
            )
        return result


class HobbiesRepository:
    def __init__(self) -> None:
        self._db = JsonDB("hobbies.json")

    def get_all(self) -> Dict[str, Hobby]:
        raw = self._db.get_all()
        return {hid: Hobby(**data) for hid, data in raw.items()}

    def save(self, hobby: Hobby) -> None:
        self._db.set(hobby.id, hobby_to_dict(hobby))

    def delete(self, hobby_id: str) -> None:
        self._db.delete(hobby_id)


class AdminRepository:
    def __init__(self) -> None:
        self._db = JsonDB("admin.json")

    def get_settings(self) -> AdminSettings:
        data = self._db.get("settings", {})
        return AdminSettings(
            admin_ids=data.get("admin_ids", []),
            required_channel_username=data.get("required_channel_username"),
        )

    def save_settings(self, settings: AdminSettings) -> None:
        self._db.set("settings", admin_to_dict(settings))


class FriendsRepository:
    """Репозиторий для управления дружбой"""
    def __init__(self) -> None:
        self._db = JsonDB("friends.json")
    
    def _get_friendship_key(self, user_id_1: int, user_id_2: int) -> str:
        """Получить уникальный ключ для пары пользователей"""
        # Сортируем, чтобы (1,2) и (2,1) были одной дружбой
        ids = sorted([user_id_1, user_id_2])
        return f"{ids[0]}_{ids[1]}"
    
    def get_friendship(self, user_id_1: int, user_id_2: int) -> Optional[Friendship]:
        """Получить информацию о дружбе между двумя пользователями"""
        key = self._get_friendship_key(user_id_1, user_id_2)
        data = self._db.get(key)
        if data:
            return Friendship(**data)
        return None
    
    def get_all_friends(self, user_id: int) -> Dict[int, Friendship]:
        """Получить всех друзей пользователя"""
        raw = self._db.get_all()
        friends = {}
        for key, data in raw.items():
            parts = key.split("_")
            if len(parts) == 2:
                friend_id_1, friend_id_2 = int(parts[0]), int(parts[1])
                if friend_id_1 == user_id:
                    friends[friend_id_2] = Friendship(**data)
                elif friend_id_2 == user_id:
                    friends[friend_id_1] = Friendship(**data)
        return friends
    
    def save_friendship(self, friendship: Friendship) -> None:
        """Сохранить/обновить информацию о дружбе"""
        key = self._get_friendship_key(friendship.user_id_1, friendship.user_id_2)
        self._db.set(key, {
            "user_id_1": friendship.user_id_1,
            "user_id_2": friendship.user_id_2,
            "friendship_level": friendship.friendship_level,
            "total_sessions_together": friendship.total_sessions_together,
            "first_met_date": friendship.first_met_date,
            "last_interaction": friendship.last_interaction,
            "social_bonuses": friendship.social_bonuses,
        })
    
    def delete_friendship(self, user_id_1: int, user_id_2: int) -> None:
        """Удалить дружбу"""
        key = self._get_friendship_key(user_id_1, user_id_2)
        self._db.delete(key)


class CoopSessionsRepository:
    """Репозиторий для совместных сессий"""
    def __init__(self) -> None:
        self._db = JsonDB("coop_sessions.json")
    
    def save_session(self, session: CoopSession) -> None:
        """Сохранить сессию совместной активности"""
        self._db.set(session.id, {
            "id": session.id,
            "activity_type": session.activity_type,
            "user_ids": session.user_ids,
            "start_time": session.start_time,
            "duration_minutes": session.duration_minutes,
            "result_happiness": session.result_happiness,
            "result_money": session.result_money,
            "event_triggered": session.event_triggered,
        })
    
    def get_user_coop_history(self, user_id: int, limit: int = 10) -> List[CoopSession]:
        """Получить историю совместных активностей пользователя"""
        raw = self._db.get_all()
        sessions = []
        for data in raw.values():
            if user_id in data.get("user_ids", []):
                sessions.append(CoopSession(**data))
        # Сортируем по времени, новые в начале
        sessions.sort(key=lambda s: s.start_time, reverse=True)
        return sessions[:limit]

