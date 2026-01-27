from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict

from bot.storage.json_db import JsonDB


@dataclass
class UserStats:
    user_id: int
    total_sleep_minutes: int = 0
    feed_events: int = 0
    water_events: int = 0
    work_sessions: int = 0
    hobby_sessions: int = 0


class StatsRepository:
    def __init__(self) -> None:
        self._db = JsonDB("stats.json")

    def _load_all(self) -> Dict[str, UserStats]:
        raw = self._db.get_all()
        return {uid: UserStats(**data) for uid, data in raw.items()}

    def _save_all(self, stats: Dict[str, UserStats]) -> None:
        self._db._write({uid: asdict(s) for uid, s in stats.items()})  # type: ignore

    def _get_or_create(self, user_id: int) -> UserStats:
        stats = self._load_all()
        key = str(user_id)
        if key not in stats:
            stats[key] = UserStats(user_id=user_id)
            self._save_all(stats)
        return stats[key]
    
    def get_user_stats(self, user_id: int) -> UserStats:
        """Публичный метод для получения статистики пользователя."""
        return self._get_or_create(user_id)

    def inc_feed(self, user_id: int) -> None:
        stats = self._load_all()
        s = self._get_or_create(user_id)
        s.feed_events += 1
        stats[str(user_id)] = s
        self._save_all(stats)

    def inc_water(self, user_id: int) -> None:
        stats = self._load_all()
        s = self._get_or_create(user_id)
        s.water_events += 1
        stats[str(user_id)] = s
        self._save_all(stats)

    def inc_work(self, user_id: int) -> None:
        stats = self._load_all()
        s = self._get_or_create(user_id)
        s.work_sessions += 1
        stats[str(user_id)] = s
        self._save_all(stats)

    def inc_hobby(self, user_id: int) -> None:
        stats = self._load_all()
        s = self._get_or_create(user_id)
        s.hobby_sessions += 1
        stats[str(user_id)] = s
        self._save_all(stats)

    def add_sleep_minutes(self, user_id: int, minutes: int) -> None:
        stats = self._load_all()
        s = self._get_or_create(user_id)
        s.total_sleep_minutes += max(0, minutes)
        stats[str(user_id)] = s
        self._save_all(stats)

    def get_all(self) -> Dict[str, UserStats]:
        return self._load_all()

